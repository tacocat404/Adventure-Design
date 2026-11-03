"""AI 분석 (API 명세 05절 계약 · AI 실험 계획 07절).

판단 (로컬): 키워드 규칙 + kor_unsmile(smilegate-ai, 한국어 악플 BERT). 둘 중 하나라도 거칠다고 보면 가린다.
작성 (API): 충남대 AI 포털 게이트웨이(backend/.env). 이름을 바꾸고 거친 구절을 가린 문장만 보낸다.
torch · transformers가 없거나 .env 키가 없으면 키워드 규칙만으로 돈다 (앱은 멈추지 않음).
"""
import json
import os
import re
import threading
import urllib.request
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
ENV = {**{k.strip(): v.strip() for k, _, v in (l.partition("=") for l in (ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []))
          if k.strip() and not k.startswith("#")}, **os.environ}

LOCAL_NAME = "smilegate-ai/kor_unsmile"
TOXIC_MIN = 0.3  # 1 - clean 점수가 이 값 이상이면 거침. 0.3 · 0.4 모두 과잉 가림 0.03, 재현율은 0.3이 높음 (ml/results.md)
LLM_TIMEOUT = 5  # 분석: 5초 넘으면 1번 재시도 (유저플로우 B). 보내기 전 검사는 4초 1번만

# 거친 표현 (가림 대상)
ROUGH = ["제대로 못", "그러고도", "자격", "무능", "한심", "미친", "꺼져", "개념", "똑바로",
         "멍청", "바보", "쓰레기", "정신 차", "돌았", "월급 받", "씨발", "시발", "ㅅㅂ", "병신", "ㅂㅅ"]
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
REQUEST = ["주세요", "해 주", "부탁", "알려", "싶어요", "할까요", "있을까요", "바랍니다", "주실"]

# 쉼표 · 마침표 · 물음표 · 느낌표 단위 구절
CLAUSE = re.compile(r"[^,.?!\n]+[,.?!]*")


def _clauses(text):
    out = []
    for m in CLAUSE.finditer(text):
        raw = m.group()
        lead = len(raw) - len(raw.lstrip())
        if raw.strip():
            out.append((m.start() + lead, m.end(), raw.strip()))
    return out


def _hits(s, words):
    flat = re.sub(r"\s+", "", s)  # 띄어쓰기가 달라도 잡는다 (죽고싶다 · 죽고 싶다)
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
    threading.Thread(target=_load, daemon=True).start()


def toxic_scores(sentences):
    """문장마다 1 - clean 점수. 로컬 모델이 없으면 None."""
    mdl = _load()
    if not mdl or not sentences:
        return None
    torch, tok, m, clean = mdl
    with torch.no_grad():
        p = torch.sigmoid(m(**tok(sentences, return_tensors="pt", padding=True, truncation=True, max_length=128)).logits)
    return [1 - float(r[clean]) for r in p]


def rough_flags(sentences, mode="both"):
    """mode: keyword · local · both (평가에서 셋을 비교)."""
    kw = [_hits(s, ROUGH + THREAT) for s in sentences]
    if mode == "keyword":
        return kw
    sc = toxic_scores(sentences)
    lm = [x >= TOXIC_MIN for x in sc] if sc else [False] * len(sentences)
    return lm if mode == "local" else [a or b for a, b in zip(kw, lm)]


def judge_name():
    return "kor_unsmile+keyword" if _load() else "keyword"


# ───────── 작성: 충남대 API ─────────
SUMMARY_SYS = """너는 학교 소통 앱 '쿠션톡'의 분류 · 요약 도우미야. 학부모가 담임에게 보낸 메시지를 읽어.
1) category를 골라.
   - urgent: 학생이 위험한 상황 — 학교폭력(신체 · 언어 · 금전 피해), 아동학대 · 방임, 학생의 신체 · 생명 안전(사고, 행방 불명, 자해 위험, 위험한 시설)
   - threat: 교사 · 학교를 향한 교권 침해성 위협. 유형 — 신체적 위해 암시, 학교 · 교사를 찾아가겠다는 대면 압박, 신상 공개 · 명예 훼손 위협, 법적 · 행정 조치를 무기로 한 압박, "~하면 가만있지 않겠다" 같은 조건부 경고, 끝까지 문제 삼겠다는 압박. 정중하거나 돌려 말해도 위협이면 threat. 확신이 없으면 threat를 골라 — 놓치는 것보다 사람이 한 번 더 보는 게 낫다.
   - normal: 그 밖의 요청 · 문의 · 항의 (무례해도 위협이 아니면 normal)
2) summary: 담임이 할 일을 해요체 한 문장으로. 요청이 있으면 "~해 달라는 요청이에요.", 없으면 "~라는 내용이에요."로 끝내. 위협이면 무엇을 하겠다는지 담담하게 적어.
- [가림N]은 모욕 표현을 가려 둔 자리야. 요약에 넣지 마. [이름N]은 사람 이름이야. 그대로 써.
- 요청은 하나도 빼지 말고, 메시지에 없는 내용은 지어내지 마.
3) request_summary: 담임이 정당하게 처리할 수 있는 요청만 해요체 한 문장으로 (예: 자리 변경 · 상담 · 준비물 문의 · 숙제 양 조정). 사과 · 무릎 꿇기 같은 굴종 요구, 성적 · 평가를 바꾸라는 압박, 찾아오겠다 · 신고하겠다는 협박은 요청이 아니야 — 절대 넣지 마. 정당한 요청이 하나도 없으면 null.
4) requests: 위의 정당한 요청만 짧게 (없으면 []).
JSON만 출력해: {"category": "urgent|threat|normal", "urgent_type": "school_violence|child_abuse|safety|null", "reason": "urgent · threat로 본 이유 한 문장 (normal이면 null)", "summary": "...", "request_summary": "... 또는 null", "requests": ["짧은 요청", ...]}"""

SOFTEN_SYS = """학부모가 담임에게 보내려는 메시지를 예의 바르게 고쳐 줘.
- [가림N]은 거친 표현이 있던 자리야. 빼고 써.
- [이름N]은 사람 이름이야. 그대로 써.
- 요청 · 사실 · 기한은 하나도 빼거나 바꾸지 말고, 없는 내용을 더하지 마.
- 학부모 말투(해요체)로, 원래 길이와 비슷하게. 서로 다른 두 가지로.
JSON만 출력해: {"suggestions": ["고친 메시지 1", "고친 메시지 2"], "keeps": ["그대로 전해지는 요청을 짧게", ...]}"""


def writer_name():
    return ENV.get("CNU_MODEL") if ENV.get("CNU_API_KEY") else None


def _llm(system, user, tries=2, timeout=LLM_TIMEOUT):
    if not writer_name():
        return None
    body = {"model": ENV["CNU_MODEL"], "max_tokens": 1500, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(ENV.get("CNU_BASE_URL", "").rstrip("/") + "/chat/completions/", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + ENV["CNU_API_KEY"], "Content-Type": "application/json"})
    for _ in range(tries):
        try:
            txt = json.load(urllib.request.urlopen(req, timeout=timeout))["choices"][0]["message"]["content"]
            return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
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
def _judge(text):
    """화면에서 가릴 구간 · API로 보낼 때 가릴 구간(위협 구절은 요약할 내용이라 빼고) · 요청 · 나머지."""
    cl = _clauses(text)
    flags = rough_flags([s for _, _, s in cl])
    spans = [{"start": a, "end": b} for (a, b, _), f in zip(cl, flags) if f]
    api_spans = [{"start": a, "end": b} for (a, b, s), f in zip(cl, flags) if f and not _hits(s, THREAT)]
    requests = [s for (_, _, s), f in zip(cl, flags) if not f and _hits(s, REQUEST)]
    rest = [s for (_, _, s), f in zip(cl, flags) if not f]
    return spans, api_spans, requests, rest


def precheck(text: str, names=()) -> dict:
    spans, _, keeps, _ = _judge(text)
    out = {"rough": bool(spans), "spans": spans, "suggestions": [], "keeps": keeps}
    if spans:
        hidden, pairs = _hide(text, spans, names)
        r = _llm(SOFTEN_SYS, hidden, tries=1, timeout=4)  # 5초 규칙: 학부모가 기다리는 중이라 다시 묻지 않음
        if r and r.get("suggestions"):
            out["suggestions"] = [_show(s, pairs) for s in r["suggestions"][:2] if s]
            out["keeps"] = [_show(k, pairs) for k in r.get("keeps", [])] or keeps
        else:
            soft = _soften(text, spans)
            out["suggestions"] = [soft] if soft else []
    return out


SEVERITY = {"normal": 0, "threat": 1, "urgent": 2}


def analyze(original_text: str, names=(), use_api=True) -> dict:
    urgent_type = next((t for t, ws in URGENT.items() if _hits(original_text, ws)), None)
    threat_words = [w for w in THREAT if _hits(original_text, [w])]
    category = "urgent" if urgent_type else "threat" if threat_words else "normal"
    reason = ", ".join(f"‘{w}’" for w in threat_words) + " 같은 위협 표현이 들어 있어요." if threat_words else None
    spans, api_spans, requests, rest = _judge(original_text)
    summary = " ".join(requests or rest[-1:]) or "거친 표현만 있어 요약할 요청이 없어요. 원문 보기로 확인해 주세요."
    writer = None
    request_summary = " ".join(requests) or None  # 키워드만 돌 때: 거친 구절이 아닌 요청 구절
    # API도 분류를 판단한다: 키워드만으로는 위협 재현율 0.40 (ml/results.md). 더 심각한 쪽을 따른다 — 놓치는 것보다 한 번 더.
    hidden, pairs = _hide(original_text, api_spans, names)
    r = _llm(SUMMARY_SYS, hidden) if use_api else None
    if r and r.get("summary"):
        summary, requests, writer = _show(r["summary"], pairs), [_show(x, pairs) for x in r.get("requests") or []], writer_name()
        request_summary = _show(r["request_summary"], pairs) if r.get("request_summary") else None  # 교사에게 보이는 건 이 문장뿐
        api_cat = r.get("category") if r.get("category") in SEVERITY else "normal"
        if SEVERITY[api_cat] > SEVERITY[category]:
            category, reason = api_cat, _show(r.get("reason") or "", pairs) or reason
            urgent_type = r.get("urgent_type") if r.get("urgent_type") in URGENT else urgent_type or "safety"
    if category == "urgent":
        spans = []  # 긴급은 가리지 않고 원문 그대로
    return {
        "category": category,
        "urgent_type": urgent_type if category == "urgent" else None,
        "summary": summary,
        "requests": requests,
        "request_summary": request_summary,
        "masked_spans": spans,
        "threat_reason": reason if category == "threat" else None,
        "model": judge_name() + (f"/{writer}" if writer else ""),
    }


if __name__ == "__main__":
    raw = "선생님, 애들 하나 제대로 못 보세요? 우리 민서가 짝이랑 안 맞아서 매일 울면서 집에 와요. 그러고도 선생님 소리 듣고 싶으세요? 내일까지 자리 바꿔 주세요."
    r = analyze(raw, names=["민서"])
    assert r["category"] == "normal" and len(r["masked_spans"]) == 2, r
    assert [raw[s["start"]:s["end"]] for s in r["masked_spans"]][0] == "애들 하나 제대로 못 보세요?"
    assert "자리" in r["summary"], r
    assert analyze("하윤이가 쉬는 시간마다 친구들한테 맞는다고 해요.")["category"] == "urgent"
    assert analyze("내일 아침에 교실로 직접 찾아갈 테니 각오하고 계세요.")["category"] == "threat"
    p = precheck(raw, names=["민서"])
    assert p["rough"] and p["suggestions"] and all("제대로 못" not in s for s in p["suggestions"]), p
    assert not precheck("다음 주 상담 시간 잡아 주세요.")["rough"]
    h, pairs = _hide("민서가 울어요.", [], ["민서"])
    assert h == "[이름1]가 울어요." and _show(h, pairs) == "민서가 울어요."
    print("analyzer ok ·", r["model"], "·", r["summary"], "·", p["suggestions"][0])
