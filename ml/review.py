"""사람 검수 · 시험 문제 도구 (팀원용).

1) 검수표 만들기:  python ml/review.py sheet  → ml/review/검수표_A.csv · 검수표_B.csv (같은 1,000문장, 순서만 다름)
   두 사람이 서로 보지 않고 rough · category 칸을 채운다. AI 라벨은 표에 안 넣는다 (따라 쓰지 않게).
2) 결과 보기:     python ml/review.py score  → 두 사람 합의도(Cohen κ) · AI 라벨과 일치율 · 고쳐야 할 문장
                  → ml/data/reviewed.json : 두 사람이 같은 답을 낸 문장 (train.py가 다른 파일보다 우선해 씀)
3) 시험 문제 양식: ml/review/시험문제_양식.csv — 사람이 직접 쓴 문장 300개 이상 (학습에 절대 안 씀)
"""
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
import train  # noqa: E402

DIR = ROOT / "ml" / "review"
N = 1000
COLS = ["번호", "문장", "rough (O/X)", "category (긴급/위협/일반)", "메모"]
CAT = {"긴급": "urgent", "위협": "threat", "일반": "normal"}


def sheet():
    items = train.load_items()
    by = {}
    for x in items:
        by.setdefault(x["type"], []).append(x)
    rnd = random.Random(7)
    per = max(1, N // len(by))
    pick = [x for xs in by.values() for x in rnd.sample(xs, min(per, len(xs)))]
    rest = [x for x in items if x not in pick]
    pick += rnd.sample(rest, max(0, N - len(pick)))
    pick = pick[:N]
    DIR.mkdir(parents=True, exist_ok=True)
    key = [{"번호": i + 1, "text": x["text"], "rough": x["rough"], "category": x["category"], "type": x["type"]} for i, x in enumerate(pick)]
    (DIR / "검수표_정답키.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, seed in (("A", 1), ("B", 2)):
        rows = list(key)
        random.Random(seed).shuffle(rows)
        with open(DIR / f"검수표_{name}.csv", "w", encoding="utf-8-sig", newline="") as f:  # 엑셀에서 한글 깨지지 않게 BOM
            w = csv.writer(f)
            w.writerow(COLS)
            w.writerows([[r["번호"], r["text"], "", "", ""] for r in rows])
    with open(DIR / "시험문제_양식.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["문장", "rough (O/X)", "category (긴급/위협/일반)", "쓴 사람", "메모"])
        w.writerow(["(예) 선생님 오늘 숙제 범위가 어디까지예요?", "X", "일반", "홍길동", "← 이 줄은 지우고 쓰기"])
    print(f"검수표 {len(pick)}문장 → {DIR}", Counter(x["type"] for x in pick).most_common(5))


def read(name):
    out = {}
    with open(DIR / f"검수표_{name}.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            ro, ca = r["rough (O/X)"].strip().upper(), CAT.get(r["category (긴급/위협/일반)"].strip())
            if ro in ("O", "X") and ca:
                out[int(r["번호"])] = (ro == "O", ca)
    return out


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(a) | set(b)) / n / n
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def score():
    key = {k["번호"]: k for k in json.loads((DIR / "검수표_정답키.json").read_text(encoding="utf-8"))}
    a, b = read("A"), read("B")
    both = sorted(set(a) & set(b))
    print(f"A {len(a)} · B {len(b)} · 둘 다 채운 문장 {len(both)}")
    if not both:
        return
    print(f"합의도 κ — rough {kappa([a[i][0] for i in both], [b[i][0] for i in both]):.2f} · "
          f"category {kappa([a[i][1] for i in both], [b[i][1] for i in both]):.2f}  (0.6 이상이면 괜찮음, 0.8 이상 아주 좋음)")
    agree = [i for i in both if a[i] == b[i]]
    ai_ok = sum(a[i] == (key[i]["rough"], key[i]["category"]) for i in agree)
    print(f"두 사람이 같은 답 {len(agree)} · 그중 AI 라벨과 같음 {ai_ok} ({ai_ok / max(len(agree), 1):.0%})")
    fixed = [{"text": key[i]["text"], "rough": a[i][0], "category": a[i][1], "type": key[i]["type"]} for i in agree]
    (ROOT / "ml" / "data" / "reviewed.json").write_text(json.dumps(
        {"_note": "팀원 두 명이 따로 라벨을 붙여 같은 답을 낸 문장 (AI 라벨과 다르면 사람 답으로).", "items": fixed},
        ensure_ascii=False, indent=1), encoding="utf-8")
    wrong = [(key[i]["text"], key[i]["category"], a[i][1]) for i in agree if a[i] != (key[i]["rough"], key[i]["category"])]
    print("AI 라벨이 틀린 예:", wrong[:10])


if __name__ == "__main__":
    {"sheet": sheet, "score": score}[sys.argv[1]]()
