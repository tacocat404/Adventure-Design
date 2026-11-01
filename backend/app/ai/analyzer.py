"""AI 분석 (API 명세 05절 계약). 지금은 키워드 규칙 버전.

ponytail: 키워드 사전 기반이라 문맥을 못 봄. AI 실험 계획대로
판단은 학습한 한국어 인코더, 요약 · 제안 문장은 API LLM으로 바꿀 자리.
함수 이름과 돌려주는 모양은 바꾸지 않는다.
"""
import re

MODEL = "keyword-v0"

# 거친 표현 (가림 대상)
ROUGH = ["제대로 못", "그러고도", "자격", "무능", "한심", "미친", "꺼져", "개념", "똑바로",
         "멍청", "바보", "쓰레기", "정신 차", "돌았", "월급 받", "씨발", "시발", "ㅅㅂ", "병신", "ㅂㅅ"]
# 위협 (애매해도 위협)
THREAT = ["찾아가", "찾아갈", "각오", "가만 안 두", "가만두지", "가만 있지 않", "두고 보",
          "어디 사는지", "어디 사시는지", "죽여", "고소", "신고하겠", "신고할"]
# 긴급: 학교폭력 · 아동학대 · 안전
URGENT = {
    "child_abuse": ["학대", "집에서 맞", "굶"],
    "school_violence": ["맞는다", "맞았", "때리", "때렸", "폭행", "괴롭", "왕따", "따돌"],
    "safety": ["다쳤", "위험", "무너", "화재", "자해", "자살", "실종"],
}
REQUEST = ["주세요", "해 주", "부탁", "알려", "싶어요", "할까요", "있을까요", "바랍니다", "주실"]

# 쉼표 · 마침표 · 물음표 · 느낌표 단위 구절
CLAUSE = re.compile(r"[^,.?!\n]+[,.?!]*")


def _clauses(text):
    for m in CLAUSE.finditer(text):
        raw = m.group()
        lead = len(raw) - len(raw.lstrip())
        if raw.strip():
            yield m.start() + lead, m.end(), raw.strip()


def _hits(s, words):
    return any(w in s for w in words)


def _spans(text):
    return [{"start": a, "end": b} for a, b, s in _clauses(text) if _hits(s, ROUGH + THREAT)]


def _requests(text):
    return [s for a, b, s in _clauses(text) if _hits(s, REQUEST) and not _hits(s, ROUGH + THREAT)]


def _soften(text, spans):
    out, last = [], 0
    for sp in spans:
        out.append(text[last:sp["start"]])
        last = sp["end"]
    out.append(text[last:])
    return re.sub(r"\s{2,}", " ", "".join(out)).strip()


def precheck(text: str) -> dict:
    spans = _spans(text)
    keeps = _requests(text)
    soft = _soften(text, spans) if spans else text
    return {
        "rough": bool(spans),
        "spans": spans,
        "suggestions": [soft] if spans and soft else [],
        "keeps": keeps,
    }


def analyze(original_text: str) -> dict:
    urgent_type = next((t for t, ws in URGENT.items() if _hits(original_text, ws)), None)
    threat = _hits(original_text, THREAT)
    category = "urgent" if urgent_type else "threat" if threat else "normal"
    spans = [] if category == "urgent" else _spans(original_text)
    requests = _requests(original_text)
    rest = [s for a, b, s in _clauses(original_text) if not _hits(s, ROUGH + THREAT)]
    summary = " ".join(requests or rest[-1:]) or "내용을 요약하지 못했어요."
    return {
        "category": category,
        "urgent_type": urgent_type,
        "summary": summary,
        "requests": requests,
        "masked_spans": spans,
        "threat_reason": "위협 표현이 들어 있어요: " + ", ".join(w for w in THREAT if w in original_text) if threat else None,
        "model": MODEL,
    }


if __name__ == "__main__":
    raw = "선생님, 애들 하나 제대로 못 보세요? 우리 민서가 짝이랑 안 맞아서 매일 울면서 집에 와요. 그러고도 선생님 소리 듣고 싶으세요? 내일까지 자리 바꿔 주세요."
    r = analyze(raw)
    assert r["category"] == "normal" and len(r["masked_spans"]) == 2, r
    assert [raw[s["start"]:s["end"]] for s in r["masked_spans"]][0] == "애들 하나 제대로 못 보세요?"
    assert analyze("하윤이가 쉬는 시간마다 친구들한테 맞는다고 해요.")["category"] == "urgent"
    assert analyze("내일 아침에 교실로 직접 찾아갈 테니 각오하고 계세요.")["category"] == "threat"
    p = precheck(raw)
    assert p["rough"] and "애들 하나" not in p["suggestions"][0] and "자리 바꿔 주세요" in p["suggestions"][0]
    assert not precheck("다음 주 상담 시간 잡아 주세요.")["rough"]
    print("analyzer ok")
