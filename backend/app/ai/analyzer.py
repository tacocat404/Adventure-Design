"""AI 분석 (API 명세 05절 계약 · AI 실험 계획 07절).

판단 (로컬): 키워드 규칙 + kor_unsmile(smilegate-ai, 한국어 악플 BERT). 둘 중 하나라도 거칠다고 보면 가린다.
작성 (API): 충남대 AI 포털 게이트웨이(backend/.env). 요약은 이름을 바꾸고 거친 구절을 가린 문장만, 다듬기는 이름만 바꾼 문장을 보낸다.
torch · transformers가 없거나 .env 키가 없으면 키워드 규칙만으로 돈다 (앱은 멈추지 않음).
"""
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
import urllib.error
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
ENV = {**{k.strip(): v.strip() for k, _, v in (l.partition("=") for l in (ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []))
          if k.strip() and not k.startswith("#")}, **os.environ}

LOCAL_NAME = "smilegate-ai/kor_unsmile"
TOXIC_MIN = 0.3  # 1 - clean 점수가 이 값 이상이면 거침. 0.3 · 0.4 모두 과잉 가림 0.03, 재현율은 0.3이 높음 (ml/results.md)
# 분석: 8초 넘으면 1번 재시도. 분석은 보낸 뒤 백그라운드에서 돌아 학부모 · 교사가 기다리지 않는다.
# 11.05: 요청 기준 · 이유 지시가 늘며 응답이 5초 안팎이 돼, 5초 제한이면 절반쯤 끊겨 API 요청 요약 · 이유가 버려졌다.
LLM_TIMEOUT = 8

# 거친 표현 (가림 대상)
ROUGH = ["제대로 못", "그러고도", "자격", "무능", "한심", "미친", "꺼져", "개념", "똑바로",
         "멍청", "바보", "쓰레기", "정신 차", "돌았", "월급 받", "씨발", "시발", "ㅅㅂ", "병신", "ㅂㅅ"]
# 뜻이 하나뿐인 욕설: 판단기가 뭐라 하든 가린다 (판단기는 '헷갈림' 데이터 때문에 키워드를 덜 믿게 배웠다 · stress_test 11.04)
STRONG = ["무능", "한심", "개념 없", "개념없", "꺼져", "멍청", "쓰레기", "씨발", "시발", "ㅅㅂ", "병신", "ㅂㅅ", "개새"]
# 위협 (애매해도 위협)
THREAT = ["찾아가", "찾아갈", "각오", "가만 안 두", "가만두지", "가만 있지 않", "두고 보",
          "어디 사는지", "어디 사시는지", "죽여", "고소", "신고하겠", "신고할", "가만히 안", "가만 안", "SNS에 올", "인터넷에 올", "퍼뜨리"]
# 긴급: 학교폭력 · 아동학대 · 안전
URGENT = {
    "child_abuse": ["학대", "집에서 맞", "굶"],
    "school_violence": ["맞는다", "맞았", "때리", "때렸", "폭행", "괴롭", "왕따", "따돌"],
    "safety": ["다쳤", "위험", "무너", "화재", "자해", "자살", "실종", "죽고 싶", "죽고싶", "죽을 것 같", "죽어 버리", "죽어버리", "살기 싫", "살고 싶지 않",
               "사라지고 싶", "극단적", "목숨", "스스로 해치", "손목", "유서"],
}
REQUEST = ["주세요", "해 주세요", "해 주시", "부탁", "알려", "싶어요", "할까요", "있을까요", "바랍니다", "주실",
           # 11.05: “한 번만 다시 봐주시면 안 될까요?”를 못 잡았다
           "주시면", "될까요", "봐 주", "줄 수", "주시겠", "가능할까", "괜찮을까", "해 줘", "드려도"]

HANGUL = re.compile(r"[가-힣ㄱ-ㅎ]")
# 쉼표 · 마침표 · 물음표 · 느낌표 단위 구절
CLAUSE = re.compile(r"[^,.?!\n]+[,.?!]*")
# 끊지 않는 부호: 숫자 사이(3.5점), 한 글자씩 끊어 쓴 말(개.념.없.네 — 예전엔 '개.'·'념.'으로 쪼개져 못 잡았다 · stress_test 11.04)
KEEP_DOTS = re.compile(r"(?<=\d)[.,](?=\d)|(?:(?<=^)|(?<=\s))(?:\S[.·])+\S(?=[\s.,?!]|$)")


CLAUSE_MAX = 80  # 문장 부호 없이 긴 구절은 띄어쓰기에서 60자 안팎으로 자른다 (930자 한 구절이 긴급으로 나왔다 · stress_test 11.04)


def _clauses(text):
    out = []
    # 끊지 않을 부호만 '·'로 바꾼 같은 길이 사본에서 자리를 찾고, 글자는 원문에서 가져온다
    probe = KEEP_DOTS.sub(lambda m: re.sub(r"[.,]", "·", m.group()), text)
    for m in CLAUSE.finditer(probe):
        raw = m.group()
        lead = len(raw) - len(raw.lstrip())
        if not raw.strip():
            continue
        a, b = m.start() + lead, m.start() + len(raw.rstrip())
        while b - a > CLAUSE_MAX:
            cut = text.rfind(" ", a + 20, a + 60)
            cut = cut if cut > a else a + 60
            out.append((a, cut, text[a:cut].strip()))
            a = cut + 1 if text[cut:cut + 1] == " " else cut
        out.append((a, m.end(), text[a:m.end()].strip()))
    return out


def _hits(s, words):
    flat = re.sub(r"[\s.·,_\-~*^]+", "", s)  # 띄어쓰기 · 점으로 끊어 써도 잡는다 (죽고 싶다 · 개.념.없.네)
    return any(w in s or w.replace(" ", "") in flat for w in words)


# ───────── 판단: 로컬 모델 ─────────
_model, _lock = None, threading.Lock()


def _load():
    global _model
    with _lock:
        if _model is None:
            try:
                if ENV.get("CUSHION_LOCAL_MODEL", "on") == "off":
                    raise ImportError("off")
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer
                tok = AutoTokenizer.from_pretrained(LOCAL_NAME)
                m = AutoModelForSequenceClassification.from_pretrained(LOCAL_NAME).eval()
                clean = next(i for i, v in m.config.id2label.items() if v == "clean")
                _model = (torch, tok, m, clean)
            except Exception:
                _model = False  # 패키지 · 모델이 없으면 키워드만
    return _model


def warmup():
    """서버를 켤 때 모델을 미리 올려 첫 요청이 기다리지 않게."""
    threading.Thread(target=lambda: load_judge() or _load(), daemon=True).start()


def toxic_scores(sentences):
    """문장마다 1 - clean 점수. 로컬 모델이 없으면 None."""
    mdl = _load()
    if not mdl or not sentences:
        return None
    torch, tok, m, clean = mdl
    with torch.no_grad():
        p = torch.sigmoid(m(**tok(sentences, return_tensors="pt", padding=True, truncation=True, max_length=128)).logits)
    return [1 - float(r[clean]) for r in p]


def kw_vec(s):
    """키워드 판단 [거침, 위협, 긴급] — 스태킹의 첫 번째 점수."""
    return [float(_hits(s, ROUGH + THREAT)), float(_hits(s, THREAT)), float(any(_hits(s, ws) for ws in URGENT.values()))]


# ───────── 판단: 증류 학습한 로컬 판단기 (BERT + kNN + 스태킹 · INT8) ─────────
JUDGE_DIR = Path(ENV.get("CUSHION_JUDGE_DIR") or Path(__file__).resolve().parents[3] / "ml" / "models" / "judge")
_judge_model = None


def load_judge():
    """ml/models/judge가 있으면 증류 판단기, 없거나 깨졌으면 False (그때는 kor_unsmile + 키워드로 돈다)."""
    global _judge_model
    with _lock:
        if _judge_model is None:
            try:
                if ENV.get("CUSHION_LOCAL_MODEL", "on") == "off" or not (JUDGE_DIR / "stack.json").exists():
                    raise FileNotFoundError(JUDGE_DIR)
                from app.ai.judge import Judge
                # INT8(동적 양자화)는 기본 끔: 이 CPU에서 오히려 느렸고(메시지 한 통 중앙값 56ms vs fp32 40ms),
                # 배치에 같이 들어간 문장에 따라 점수가 흔들렸다(같은 구절 긴급 0.15 ↔ 0.60 · 11.04). 비교용으로만 CUSHION_INT8=on
                _judge_model = Judge(JUDGE_DIR, quantize=ENV.get("CUSHION_INT8", "off") == "on")
            except Exception:
                _judge_model = False
    return _judge_model


def assess(sentences):
    """문장마다 {rough, threat, urgent} 판단 + 가장 비슷한 학습 문장 유형. 증류 판단기가 없으면 예전 방식."""
    if not sentences:
        return [], []
    j = load_judge()
    if j:
        # 한글이 거의 없는 구절(이모티콘만 · 영어 · 코드)은 학습한 적 없는 입력이라 모델 대신 키워드로만 본다 (stress_test 11.04)
        ok = [len(HANGUL.findall(s)) >= 2 for s in sentences]
        known = [s for s, k in zip(sentences, ok) if k]
        flags, _, types = j.predict(known, [kw_vec(s) for s in known]) if known else ([], None, [])
        it_f, it_t = iter(flags), iter(types)
        out_f, out_t = [], []
        for s, k in zip(sentences, ok):
            if k:
                f = next(it_f)
                out_f.append({**f, "rough": f["rough"] or _hits(s, STRONG)}); out_t.append(next(it_t))
            else:
                v = kw_vec(s)
                out_f.append({"rough": bool(v[0]), "threat": bool(v[1]), "urgent": bool(v[2])}); out_t.append([])
        return out_f, out_t
    rough = rough_flags(sentences, "both")
    return [{"rough": r, "threat": _hits(s, THREAT), "urgent": any(_hits(s, ws) for ws in URGENT.values())}
            for s, r in zip(sentences, rough)], [[] for _ in sentences]


def rough_flags(sentences, mode="both"):
    """mode: keyword · local · both · judge (평가에서 넷을 비교)."""
    kw = [_hits(s, ROUGH + THREAT) for s in sentences]
    if mode == "keyword":
        return kw
    if mode == "judge":
        return [f["rough"] or f["threat"] for f in assess(sentences)[0]]
    sc = toxic_scores(sentences)
    lm = [x >= TOXIC_MIN for x in sc] if sc else [False] * len(sentences)
    return lm if mode == "local" else [a or b for a, b in zip(kw, lm)]


def judge_name():
    if load_judge():
        return "judge(kor_unsmile 증류+kNN+스태킹" + (",int8)" if ENV.get("CUSHION_INT8", "off") == "on" else ")")
    return "kor_unsmile+keyword" if _load() else "keyword"


# ───────── 작성: 충남대 API ─────────
# 요약(교사에게 보임)과 보내기 전 검사(학부모에게 “이 요청은 전달돼요”로 보임)가 같은 기준을 써야 한다.
# 11.05: 요약은 “성적 · 평가 압박은 요청 아님”, 검사는 “성적 다시 확인”을 요청으로 뽑아 — 학부모에겐 전달된다고 하고 교사에겐 안 갔다.
REQUEST_RULE = """정당한 요청 = 담임이 할 수 있는 일을 부탁하는 것. 예: 자리 · 모둠 변경, 상담, 준비물 · 숙제 문의, 성적 · 채점 기준을 다시 확인하거나 설명해 달라는 것, 아이를 살펴봐 달라는 것, 일정 · 연락 요청.
위협이나 거친 말이 함께 있어도, 그 안의 요청 자체가 정당하면 넣는다 (위협 부분만 뺀다).
요청이 아닌 것 = 사과 · 무릎 꿇기 같은 굴종 요구, 점수를 올려라 · 바꿔라는 결과 강요, 찾아오겠다 · 신고하겠다 · 퍼뜨리겠다는 협박."""

SUMMARY_SYS = """너는 학교 소통 앱 '쿠션톡'의 분류 · 요약 도우미야. 학부모가 담임에게 보낸 메시지를 읽어.
1) category를 골라.
   - urgent: 학생이 위험한 상황 — 학교폭력(신체 · 언어 · 금전 피해), 아동학대 · 방임, 학생의 신체 · 생명 안전(사고, 행방 불명, 자해 위험, 위험한 시설)
   - threat: 교사 · 학교를 향한 교권 침해성 위협. 유형 — 신체적 위해 암시, 학교 · 교사를 찾아가겠다는 대면 압박, 신상 공개 · 명예 훼손 위협, 법적 · 행정 조치를 무기로 한 압박, "~하면 가만있지 않겠다" 같은 조건부 경고, 끝까지 문제 삼겠다는 압박. 정중하거나 돌려 말해도 위협이면 threat. 확신이 없으면 threat를 골라 — 놓치는 것보다 사람이 한 번 더 보는 게 낫다.
   - normal: 그 밖의 요청 · 문의 · 항의 (무례해도 위협이 아니면 normal)
2) summary: 담임이 할 일을 해요체 한 문장으로. 요청이 있으면 "~해 달라는 요청이에요.", 없으면 "~라는 내용이에요."로 끝내. 위협이면 무엇을 하겠다는지 담담하게 적어.
- [가림N]은 모욕 표현을 가려 둔 자리야. 요약에 넣지 마. [이름N]은 사람 이름이야. 그대로 써.
- 요청은 하나도 빼지 말고, 메시지에 없는 내용은 지어내지 마.
3) request_summary: 정당한 요청만 해요체 한 문장으로 ("~해 달라는 요청이에요."). 정당한 요청이 하나도 없을 때만 null.
""" + REQUEST_RULE + """
4) requests: 위의 정당한 요청만 짧게 (없으면 []).
5) reason: urgent · threat로 본 이유 한 문장. 무엇이 왜 문제인지 구체적으로 — 어떤 요구에 어떤 압박을 붙였는지 (예: "성적 재검토를 요구하면서 교육청 보고를 압박 수단으로 썼어요."). normal이면 null.
JSON만 출력해: {"category": "urgent|threat|normal", "urgent_type": "school_violence|child_abuse|safety|null", "reason": "... 또는 null", "summary": "...", "request_summary": "... 또는 null", "requests": ["짧은 요청", ...]}"""

SOFTEN_SYS = """학부모가 담임에게 보내려는 메시지에 거친 표현이나 위협이 섞여 있어. 담임이 기분 상하지 않게 예의 바른 메시지로 다시 써 줘.
- 거친 구절을 그냥 지우지 마. 그 말에 담긴 감정 · 걱정을 정중한 말로 바꿔.
  예: "애들이 얼마나 짜증나고 있는지 아세요?" → "요즘 아이들이 많이 힘들어해서 걱정이 돼요."
  예: "애들 하나 제대로 못 보세요?" → "아이들을 조금 더 살펴봐 주시면 좋겠어요."
- 위협(찾아가겠다, 각오해라, 가만있지 않겠다, 신고 · 고소 압박, 그렇게 아세요)은 반드시 빼. 만나서 이야기하고 싶다는 뜻이면 "필요하면 상담을 요청드리고 싶어요."처럼 정중하게 바꿔.
- 비꼼 · 반말 · 느낌표 남발 · 맞춤법 · 띄어쓰기도 고쳐.
- [이름N]은 사람 이름이야. 그대로 써.
- 요청 · 사실 · 기한은 하나도 빼거나 바꾸지 말고, 없는 요청을 지어내지 마.
- 학부모 말투(해요체)로. 서로 다른 두 가지로.
keeps에는 담임에게 그대로 전해지는 정당한 요청만 짧게 적어 (위협 · 감정 표현은 넣지 마).
""" + REQUEST_RULE + """
JSON만 출력해: {"suggestions": ["고친 메시지 1", "고친 메시지 2"], "keeps": ["짧은 요청", ...]}"""


def writer_name():
    return ENV.get("CNU_MODEL") if ENV.get("CNU_API_KEY") else None


_POOL = ThreadPoolExecutor(8, thread_name_prefix="llm")


def _llm(system, user, tries=2, timeout=LLM_TIMEOUT):
    if not writer_name():
        return None
    body = {"model": ENV["CNU_MODEL"], "max_tokens": 1500, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(ENV.get("CNU_BASE_URL", "").rstrip("/") + "/chat/completions/", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + ENV["CNU_API_KEY"], "Content-Type": "application/json"})
    for _ in range(tries):
        try:
            # urlopen의 timeout은 '한 번 읽을 때'만 재서, 서버가 조금씩 흘려보내면 끝없이 기다린다 (평가가 20분 멈춤 · 11.04)
            # → 응답 전체에 시간 상한을 건다. 넘으면 버리고 다음 시도 / 로컬 결과로.
            fut = _POOL.submit(lambda: json.load(urllib.request.urlopen(req, timeout=timeout)))
            txt = fut.result(timeout=timeout + 1)["choices"][0]["message"]["content"]
            return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        except urllib.error.URLError as e:
            if not isinstance(e.reason, TimeoutError):
                break  # 서버가 아예 안 받으면(끊김) 다시 물어도 같다 — 바로 로컬 결과로 (stress_test 11.04: 4.2초 → 즉시)
        except Exception:
            continue  # 시간 초과 · 형식 오류 → 한 번 더, 그래도 안 되면 키워드 버전
    return None


def _hide(text, spans, names):
    """거친 구절 → [가림N], 이름 → [이름N]. API에는 이것만 보낸다."""
    out, last = [], 0
    for i, sp in enumerate(spans, 1):
        out += [text[last:sp["start"]], f"[가림{i}]"]
        last = sp["end"]
    hidden = "".join(out) + text[last:]
    pairs = []
    for i, n in enumerate(sorted({n for n in names if n}, key=len, reverse=True), 1):
        hidden = hidden.replace(n, f"[이름{i}]")
        pairs.append((f"[이름{i}]", n))
    return hidden, pairs


def _show(s, pairs):
    for tag, n in pairs:
        s = s.replace(tag, n)
    return s


def _soften(text, spans):
    out, last = [], 0
    for sp in spans:
        out.append(text[last:sp["start"]])
        last = sp["end"]
    out.append(text[last:])
    return re.sub(r"\s{2,}", " ", "".join(out)).strip()


# ───────── 05절 계약 ─────────
PAIRS_MAX = 12  # 이웃 구절 묶음은 앞에서 12개까지 (아주 긴 글에서 느려지지 않게)


def _assess_text(text):
    """구절마다 판단 + 이웃한 두 구절을 이은 판단(“집에 안 왔어요. 연락이 안 돼요.”처럼 이어야 보이는 긴급 · 위협용).
    (구절, 구절 판단, 구절 유형, 묶음 판단 목록, 묶음 유형 목록) — 묶음은 분류에만 쓰고 가림에는 안 쓴다.
    메시지 통째로 넣지 않는 이유: 학습 문장은 짧아서, 긴 글을 통째로 넣으면 엉뚱하게 긴급이 떴다 (stress_test 11.04)."""
    cl = _clauses(text)
    sents = [s for _, _, s in cl]
    pairs = [sents[i] + " " + sents[i + 1] for i in range(min(len(sents) - 1, PAIRS_MAX))]
    flags, types = assess(sents + pairs)
    n = len(sents)
    # 거친 구절이 낀 묶음은 긴급 근거로 안 쓴다: 교사를 탓하는 말 + 아이 걱정을 이으면 학습에 없던 문장이 돼
    # “짝이랑 안 맞아서 매일 울면서 와요”(구절만은 긴급 0.02)가 묶음에서 긴급 0.87이 됐다 (시연 문장 · 11.04)
    rough = [f["rough"] or f["threat"] for f in flags[:n]]
    pair_flags = [{**f, "urgent": f["urgent"] and not (rough[i] or rough[i + 1])} for i, f in enumerate(flags[n:])]
    return cl, flags[:n], types[:n], pair_flags, types[n:]


def _judge(text, _pre=None):
    """화면에서 가릴 구간 · API로 보낼 때 가릴 구간(위협 구절은 요약할 내용이라 빼고) · 요청 · 나머지."""
    cl, flags = (_pre or _assess_text(text))[:2]
    hide = [f["rough"] or f["threat"] for f in flags]
    spans = [{"start": a, "end": b} for (a, b, _), h in zip(cl, hide) if h]
    api_spans = [{"start": a, "end": b} for (a, b, _), h, f in zip(cl, hide, flags) if h and not f["threat"]]
    requests = [s for (_, _, s), h in zip(cl, hide) if not h and _hits(s, REQUEST)]
    rest = [s for (_, _, s), h in zip(cl, hide) if not h]
    return spans, api_spans, requests, rest


URGENT_OF = {"긴급_학폭": "school_violence", "긴급_학대": "child_abuse", "긴급_자해": "safety", "긴급_안전": "safety"}
# kNN 이웃 유형 → 왜 위협인지 (판단 이유에 걸린 구절과 함께 쓴다)
THREAT_OF = {"위협_신체": "몸을 해칠 수 있다고 암시해요", "위협_대면": "학교 · 교사를 찾아가겠다며 압박해요",
             "위협_신상": "교사의 신상을 퍼뜨리겠다고 해요", "위협_법적": "신고 · 민원 · 소송을 압박 수단으로 써요",
             "위협_조건부": "들어주지 않으면 가만있지 않겠다고 경고해요", "위협_요청섞임": "요구를 들어주지 않으면 불이익을 주겠다는 뜻이에요",
             "위협_돌려말하기": "교사의 사생활을 아는 척하며 압박해요"}


def _quote(s, n=40):
    s = s.strip()
    return "‘" + (s if len(s) <= n else s[:n].rstrip() + "…") + "’"


def _threat_reason(cl, flags, types, pair_flags, pair_types, api_reason):
    """판단 이유 = ‘걸린 구절’ — 왜. 구절은 서버가 위협으로 본 곳(없으면 묶음 · 키워드), 왜는 API 이유 → kNN 유형 → 기본 문구.
    11.05: “법적 조치로 압박하는 표현과 비슷한 문장이 있어요”만으로는 어디가 문제인지 알 수 없었다."""
    hit = [s for (_, _, s), f in zip(cl, flags) if f.get("threat")]
    hit_types = [t for f, t in zip(flags, types) if f.get("threat")]
    if not hit:  # 두 구절을 이어야 보이는 위협
        sents = [s for _, _, s in cl]
        hit = [sents[i] + " " + sents[i + 1] for i, f in enumerate(pair_flags) if f.get("threat")]
        hit_types = [t for f, t in zip(pair_flags, pair_types) if f.get("threat")]
    if not hit:  # 서버는 못 봤고 키워드 · API만 위협이라고 할 때
        hit = [s for _, _, s in cl if _hits(s, THREAT)]
    why = (api_reason or "").strip() or _nearest(hit_types, THREAT_OF) or "교사를 향한 위협으로 볼 수 있어 학교에서 한 번 더 확인해요."
    if not hit:
        return why
    more = f" 외 {len(hit) - 1}곳" if len(hit) > 1 else ""
    return f"{_quote(hit[0])}{more} — {why}"


def _rough_reason(text, spans):
    """위협은 아니지만 거친 표현을 고치지 않고 보내 학교로 넘어간 메시지의 판단 이유 (11.05: 관리자 화면에 빈칸으로 떴다)."""
    first = text[spans[0]["start"]:spans[0]["end"]]
    more = f" 외 {len(spans) - 1}곳" if len(spans) > 1 else ""
    return f"{_quote(first)}{more} — 교사를 향한 거친 표현을 고치지 않고 보냈어요."


def _request_sentence(items):
    items = [i.strip().rstrip(".?!~ ") for i in items if i and i.strip()]
    return ("요청: " + " · ".join(items)) if items else None


def _nearest(types, table):
    """kNN 이웃 중 가장 많은 유형 (표에 있는 것만)."""
    got = [table[t] for row in types for t in row if t in table]
    return max(set(got), key=got.count) if got else None


SOFTEN_TIMEOUT = 15  # 다듬기는 7초 안팎 걸린다 (11.04 측정). 4초 제한이면 늘 실패해 구절만 지운 문장이 나갔다


def precheck(text: str, names=()) -> dict:
    spans, _, keeps, _ = _judge(text)
    out = {"rough": bool(spans), "spans": spans, "suggestions": [], "keeps": keeps}
    if spans:
        # 다듬기는 거친 구절의 뜻을 알아야 순화할 수 있어 이름만 바꾸고 보낸다 (가림 없이). 결과는 저장하지 않는다.
        hidden, pairs = _hide(text, [], names)
        r = _llm(SOFTEN_SYS, hidden, tries=1, timeout=SOFTEN_TIMEOUT)
        if r and r.get("suggestions"):
            out["suggestions"] = [_show(s, pairs) for s in r["suggestions"][:2] if s]
            out["keeps"] = [_show(k, pairs) for k in r.get("keeps", [])] or keeps
        else:
            soft = _soften(text, spans)  # API가 안 될 때만: 거친 구절을 뺀 문장
            out["suggestions"] = [soft] if soft else []
    return out


SEVERITY = {"normal": 0, "threat": 1, "urgent": 2}


def analyze(original_text: str, names=(), use_api=True) -> dict:
    pre = _assess_text(original_text)
    cl, flags, types, pair_flags, pair_types = pre
    all_flags, all_types = flags + pair_flags, types + pair_types
    is_urgent = any(f.get("urgent") for f in all_flags)
    is_threat = any(f.get("threat") for f in all_flags)
    kw_urgent = next((t for t, ws in URGENT.items() if _hits(original_text, ws)), None)
    urgent_type = (kw_urgent or _nearest([t for f, t in zip(all_flags, all_types) if f.get("urgent")], URGENT_OF) or "safety") if is_urgent else None
    category = "urgent" if is_urgent else "threat" if is_threat else "normal"
    api_reason = None
    spans, api_spans, requests, rest = _judge(original_text, pre)
    summary = " ".join(requests or rest[-1:]) or "거친 표현만 있어 요약할 요청이 없어요. 원문 보기로 확인해 주세요."
    writer = None
    local_requests = list(requests)  # 서버가 찾은 요청 구절 (거친 구절은 뺀 것)
    request_summary = _request_sentence(local_requests)
    # API도 분류를 판단한다: 키워드만으로는 위협 재현율 0.40 (ml/results.md). 더 심각한 쪽을 따른다 — 놓치는 것보다 한 번 더.
    hidden, pairs = _hide(original_text, api_spans, names)
    r = _llm(SUMMARY_SYS, hidden) if use_api else None
    if r and r.get("summary"):
        summary, writer = _show(r["summary"], pairs), writer_name()
        api_requests = [_show(x, pairs) for x in r.get("requests") or [] if isinstance(x, str)]
        requests = api_requests
        # 교사에게 보이는 건 이 문장뿐 — API 요약 → API 요청 목록. API가 “요청 없음”이라고 답했으면 그대로 믿는다:
        # 서버 키워드는 “이해해 주셔서 감사해요”도 요청으로 잡는다 (11.05). 서버 요청 구절은 API가 응답하지 못했을 때만.
        request_summary = (_show(r["request_summary"], pairs) if isinstance(r.get("request_summary"), str) and r["request_summary"].strip()
                           and r["request_summary"].strip() not in ("null", "None") else _request_sentence(api_requests))
        api_cat = r.get("category") if r.get("category") in SEVERITY else "normal"
        api_reason = _show(r.get("reason") or "", pairs) if isinstance(r.get("reason"), str) and r.get("reason") not in ("null", "None") else None
        if SEVERITY[api_cat] > SEVERITY[category]:
            category = api_cat
            urgent_type = r.get("urgent_type") if r.get("urgent_type") in URGENT else urgent_type or "safety"
    if category == "urgent":
        spans = []  # 긴급은 가리지 않고 원문 그대로
    reason = (_threat_reason(cl, flags, types, pair_flags, pair_types, api_reason) if category == "threat"
              else _rough_reason(original_text, spans) if category == "normal" and spans else None)
    return {
        "category": category,
        "urgent_type": urgent_type if category == "urgent" else None,
        "summary": summary,
        "requests": requests,
        "request_summary": request_summary,
        "masked_spans": spans,
        "threat_reason": reason,  # 위협이면 왜 위협인지, 거친 표현을 그대로 보낸 일반 메시지면 어디가 거친지 (둘 다 학교로 넘어간다)
        "model": judge_name() + (f"/{writer}" if writer else ""),
    }


if __name__ == "__main__":
    raw = "선생님, 애들 하나 제대로 못 보세요? 우리 민서가 짝이랑 안 맞아서 매일 울면서 집에 와요. 그러고도 선생님 소리 듣고 싶으세요? 내일까지 자리 바꿔 주세요."
    r = analyze(raw, names=["민서"])
    assert r["category"] == "normal" and len(r["masked_spans"]) == 2, r
    assert [raw[s["start"]:s["end"]] for s in r["masked_spans"]][0] == "애들 하나 제대로 못 보세요?"
    assert "자리" in r["summary"], r
    assert r["threat_reason"] and "제대로 못" in r["threat_reason"], r  # 거친 표현을 그대로 보냈으면 어디가 거친지
    assert analyze("하윤이가 쉬는 시간마다 친구들한테 맞는다고 해요.")["category"] == "urgent"
    # 11.05: 위협이 섞여도 정당한 요청은 교사에게 가고, 판단 이유는 걸린 구절을 인용한다 (API 없이도)
    g = "선생님, 우리 애가 이번 성적 때문에 많이 힘들어하는데, 한 번만 다시 봐주시면 안 될까요? 이런 일까지 교육청에 말씀드리고 싶진 않거든요."
    for use in (False, True):
        rg = analyze(g, names=["민서"], use_api=use)
        assert rg["category"] == "threat" and rg["request_summary"] and "교육청" not in rg["request_summary"], rg
        assert "교육청" in rg["threat_reason"] and "‘" in rg["threat_reason"], rg
    assert analyze("내일 아침에 교실로 직접 찾아갈 테니 각오하고 계세요.")["category"] == "threat"
    p = precheck(raw, names=["민서"])
    assert p["rough"] and p["suggestions"] and all("제대로 못" not in s for s in p["suggestions"]), p
    assert not precheck("다음 주 상담 시간 잡아 주세요.")["rough"]
    h, pairs = _hide("민서가 울어요.", [], ["민서"])
    assert h == "[이름1]가 울어요." and _show(h, pairs) == "민서가 울어요."
    print("analyzer ok ·", r["model"], "·", r["summary"], "·", p["suggestions"][0])
