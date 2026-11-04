"""증류용 학습 데이터 만들기 — 교사 모델(충남대 API LLM)이 문장을 쓰고, 다시 따로 라벨을 붙여 두 번 다 맞는 것만 남긴다.

실행 (레포 루트): backend/.venv/Scripts/python ml/gen_data.py
결과: ml/data/train.json  ({"text", "rough", "category", "type"})
평가셋(ml/eval_set.json)과 겹치거나 아주 비슷한 문장은 뺀다 — 평가 점수가 부풀지 않게.
"""
import json
import random
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai import analyzer as ai  # noqa: E402

OUT = ROOT / "ml" / "data" / "train.json"
PER_CALL = 30

# (유형, 거친 구절인가, 분류, 설명, 호출 수)
TYPES = [
    ("욕설", True, "normal", "교사를 향한 직접적인 욕설 · 모욕 · 인격 비하 (예: 무능하다, 한심하다, 자격 없다 같은 말을 여러 방식으로)", 3),
    ("비꼼", True, "normal", "교사를 향한 비꼼 · 빈정거림 · 조롱. 욕은 없지만 교사를 깎아내리는 말투 (예: '참 대단하시네요', '그것도 일이라고 하세요?')", 4),
    ("반말무례", True, "normal", "교사에게 반말 · 명령조 · 고압적으로 몰아붙이는 말 (예: '빨리 처리해', '똑바로 좀 해요')", 2),
    ("위협_신체", True, "threat", "교사에게 신체적 위해를 암시하는 말. 돌려 말하는 것 포함 (예: '밤길 조심하세요')", 2),
    ("위협_대면", True, "threat", "학교 · 교실 · 교사 집에 찾아가겠다는 압박", 2),
    ("위협_신상", True, "threat", "교사 이름 · 사진 · 사는 곳을 인터넷 · SNS · 맘카페에 퍼뜨리겠다는 위협", 2),
    ("위협_법적", True, "threat", "고소 · 교육청 민원 · 신고 · 변호사를 무기로 한 압박", 2),
    ("위협_조건부", True, "threat", "'~하면 가만있지 않겠다', '그땐 저도 몰라요', '끝까지 가겠다' 같은 조건부 경고", 3),
    ("긴급_학폭", False, "urgent", "학부모가 담임에게 알리는 학교폭력 피해 — 맞음, 괴롭힘, 따돌림, 돈 · 물건 뺏김, 사이버 괴롭힘", 3),
    ("긴급_학대", False, "urgent", "아동학대 · 방임이 의심되는 상황을 알리는 말 (다른 집 아이 걱정 포함)", 2),
    ("긴급_자해", False, "urgent", "아이가 자해 · 자살 · 죽고 싶다는 말을 하거나 그런 낌새가 있어 걱정하는 말", 2),
    ("긴급_안전", False, "urgent", "아이가 다쳤거나, 하교 후 연락이 안 되거나, 학교 시설이 위험하다는 알림", 2),
    # 짧은 긴급 · 위협: 처음 만든 긴급 문장은 길고(중앙값 64자) 함정 문장은 짧아(34자), 모델이 '짧으면 평범'을 배웠다 (11.04)
    ("긴급_학폭", False, "urgent", "학교폭력 피해를 알리는 아주 짧은 한 문장 (10~35자, 인사 없이). 맞음 · 괴롭힘 · 돈 뺏김 · 따돌림", 0),
    ("긴급_학대", False, "urgent", "아동학대 · 방임이 의심된다는 아주 짧은 한 문장 (10~35자, 인사 없이)", 0),
    ("긴급_자해", False, "urgent", "아이가 자해 · 죽고 싶다는 말을 해 걱정된다는 아주 짧은 한 문장 (10~35자, 인사 없이)", 0),
    ("긴급_안전", False, "urgent", "아이가 다쳤거나 연락이 안 되거나 시설이 위험하다는 아주 짧은 한 문장 (10~35자, 인사 없이)", 0),
    ("위협_대면", True, "threat", "학교 · 교실로 찾아가겠다는 아주 짧은 압박 한 문장 (10~35자)", 0),
    ("위협_법적", True, "threat", "고소 · 민원 · 신고로 압박하는 아주 짧은 한 문장 (10~35자)", 0),
    ("위협_조건부", True, "threat", "'~하면 가만 안 있겠다'류의 아주 짧은 조건부 경고 한 문장 (10~35자)", 0),
    ("일반_요청", False, "normal", "정중한 요청 · 문의 (자리 변경, 상담, 준비물, 숙제, 결석, 급식, 체험학습)", 3),
    ("일반_속상함", False, "normal", "아이 일로 속상하거나 걱정되는 마음을 정중하게 말하는 문장. 교사를 탓하지 않음", 3),
    ("일반_항의", False, "normal", "불만이나 항의지만 예의를 지키고 위협 · 모욕이 없는 문장", 2),
    # 11.04 시연 문장(“짝이랑 안 맞아서 매일 울면서 와요”)이 긴급, “그러고도 선생님 소리 듣고 싶으세요?”가 위협으로 나와 더한 유형
    ("일반_아이속상", False, "normal", "아이가 친구 · 짝 · 모둠과 안 맞거나, 성적 · 꾸중 · 자리 문제로 속상해 울거나 학교 가기 싫어한다는 걱정. 폭력 · 괴롭힘 · 위험은 아님", 0),
    ("비꼼_자격", True, "normal", "교사 자격 · 선생님 소리 · 월급을 들먹이며 비꼬는 말. 모욕이지만 위협(찾아감 · 신고 · 해코지)은 아님", 0),
    ("일상_짧은말", False, "normal", "짧은 대답 · 인사 · 확인 · 이모티콘만 있는 말 (예: '네 알겠습니다', '감사합니다 😊', 'ㅎㅎ 넵', '확인했어요')", 2),
    ("일반_건강결석", False, "normal", "병원 진료 · 감기 · 가족 행사로 결석 · 조퇴 · 지각을 알리는 평범한 연락 (위급하지 않음)", 3),
    ("헷갈림", False, "normal", "거친 단어나 위험한 단어가 들어 있지만 실제로는 평범한 문장 (예: '시험 문제 다 맞았대요', '바빠 죽겠네요 ㅎㅎ', '때리는 장면 나오는 영화 봤대요', '신고서 양식 어디서 받아요?', '고소한 냄새 나는 급식')", 4),
]

GEN_SYS = """너는 학교 소통 앱 AI의 학습 데이터를 만드는 도우미야. 학부모가 담임 선생님에게 보내는 메시지 속 한 문장을 만든다.
- 실제처럼 다양하게: 길이 · 말투(해요체 · 반말 · 존댓말) · 맞춤법 실수 · 띄어쓰기 실수 · 초성(ㅅㅂ 등) · 이모티콘을 섞어.
- 사람 이름은 흔한 한국 이름을 써.
- 서로 겹치지 않게, 같은 표현을 반복하지 마.
JSON만 출력해: {"items": ["문장", ...]}"""

LABEL_SYS = """학부모가 담임에게 보낸 문장마다 두 가지를 판단해.
rough: 교사를 향한 욕설 · 모욕 · 비꼼 · 고압적 말투 · 위협이 들어 있어 화면에서 가려야 하면 true. 아이 걱정 · 정중한 항의 · 거친 단어가 다른 뜻으로 쓰인 경우는 false.
category:
- urgent: 학생이 위험한 상황 (학교폭력, 아동학대 · 방임, 자해 · 자살 위험, 사고 · 실종 · 위험한 시설)
- threat: 교사 · 학교를 향한 위협 (신체 위해 암시, 찾아가겠다, 신상 공개, 법적 압박, 조건부 경고, 끝까지 문제 삼겠다)
- normal: 그 밖의 모든 것
JSON만 출력해: {"labels": [{"i": 번호, "rough": true|false, "category": "urgent|threat|normal"}, ...]}"""


def ask(system, user, max_tokens=3000, timeout=60):
    body = {"model": ai.ENV["CNU_MODEL"], "max_tokens": max_tokens, "temperature": 1.0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(ai.ENV["CNU_BASE_URL"].rstrip("/") + "/chat/completions/", data=json.dumps(body).encode(),
                                 headers={"Authorization": "Bearer " + ai.ENV["CNU_API_KEY"], "Content-Type": "application/json"})
    for _ in range(3):
        try:
            txt = json.load(urllib.request.urlopen(req, timeout=timeout))["choices"][0]["message"]["content"]
            return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        except Exception as e:  # noqa: BLE001
            err = e
    print("  실패:", err)
    return None


def generate(job):
    name, rough, cat, desc, seed = job
    r = ask(GEN_SYS, f"유형: {desc}\n이 유형의 문장을 {PER_CALL}개 만들어 줘. (변형 번호 {seed})")
    return [{"text": t.strip(), "rough": rough, "category": cat, "type": name} for t in (r or {}).get("items", []) if isinstance(t, str) and t.strip()]


def relabel(batch):
    r = ask(LABEL_SYS, "\n".join(f"{i}. {x['text']}" for i, x in enumerate(batch)))
    got = {d.get("i"): d for d in (r or {}).get("labels", []) if isinstance(d, dict)}
    keep = []
    for i, x in enumerate(batch):
        d = got.get(i)
        if d and bool(d.get("rough")) == x["rough"] and d.get("category") == x["category"]:
            keep.append(x)
    return keep


def grams(s):
    s = "".join(s.split())
    return {s[i:i + 3] for i in range(len(s) - 2)} or {s}


def main():
    if not ai.writer_name():
        sys.exit("backend/.env에 CNU_API_KEY가 없어요.")
    # --add 유형:호출수 ... → 그 유형만 더 만들어 기존 train.json에 덧붙인다
    add = dict(a.split(":") for a in sys.argv[sys.argv.index("--add") + 1:]) if "--add" in sys.argv else None
    short = "--short" in sys.argv  # 짧은 긴급 · 위협(호출 수 0으로 둔 줄)만 3번씩
    append = add is not None or short
    if append and OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
    elif OUT.exists():  # 처음부터 다시 만들 때도 지우지 않고 옆에 남긴다 (11.04 덮어써서 날린 적 있음)
        OUT.replace(OUT.with_suffix(".bak.json"))
        old = {"items": []}
    else:
        old = {"items": []}
    jobs = ([(n, r, c, d, 200 + k) for n, r, c, d, calls in TYPES if calls == 0 for k in range(3)] if short else
            [(n, r, c, d, 100 + k if add else k) for n, r, c, d, calls in TYPES if (n in add if add else calls)
             for k in range(int(add[n]) if add else calls)])
    with ThreadPoolExecutor(6) as ex:
        rows = [x for part in ex.map(generate, jobs) for x in part]
    print("만든 문장", len(rows))

    ev = json.loads((ROOT / "ml" / "eval_set.json").read_text(encoding="utf-8"))
    ev_g = [grams(s["text"]) for s in ev["sentences"]] + [grams(m["text"]) for m in ev["messages"]]
    seen, uniq = {"".join(x["text"].split()) for x in old["items"]}, []
    for x in rows:
        key = "".join(x["text"].split())
        g = grams(x["text"])
        if key in seen or any(len(g & e) / len(g | e) > 0.5 for e in ev_g):
            continue
        seen.add(key)
        uniq.append(x)
    print("중복 · 평가셋과 비슷한 문장 뺀 뒤", len(uniq))

    random.Random(len(old["items"])).shuffle(uniq)
    batches = [uniq[i:i + 20] for i in range(0, len(uniq), 20)]  # 40개씩은 JSON이 자주 깨졌다
    with ThreadPoolExecutor(6) as ex:
        kept = [x for part in ex.map(relabel, batches) for x in part]
    print("교사 모델이 다시 붙인 라벨과 일치", len(kept))

    note = old.get("_note") or "LLM이 만들고 다시 라벨을 붙여 두 번 다 맞은 문장만. 실제 학부모 메시지 아님. 사람 검수 전."
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"_note": note, "items": old["items"] + kept}, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(Counter(x["type"] for x in old["items"] + kept))


if __name__ == "__main__":
    main()
