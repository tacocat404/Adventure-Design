"""큰 합성 시험셋 만들기 — 학습에 절대 쓰지 않는다 (train.py는 이 파일을 읽지 않음).

1) 생성: ml/data/gen_eval/S_*.jsonl (문장 · rough) · M_*.jsonl (메시지 · category)  ← Sonnet 에이전트
2) strip: python ml/build_eval.py strip → gen_eval/blind_S.jsonl · blind_M.jsonl (라벨 지우고 섞음)
          다른 에이전트가 처음부터 라벨 → gen_eval/label_S.jsonl ({"id", "rough"}) · label_M.jsonl ({"id", "category"})
3) merge: python ml/build_eval.py merge → ml/eval_big.json
          두 라벨이 일치하고, 학습 데이터와 비슷하지 않은 것만 (전체 자카드 0.5 · 포함률 0.7 양쪽)
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))
import train  # noqa: E402
from import_gen import grams, read_jsonl  # noqa: E402

GEN = ROOT / "ml" / "data" / "gen_eval"
OUT = ROOT / "ml" / "eval_big.json"


def rows(kind):
    out = []
    for r in read_jsonl(sorted(GEN.glob(f"{kind}_*.jsonl"))):
        t = r.get("text")
        if not isinstance(t, str) or not t.strip():
            continue
        if kind == "S" and isinstance(r.get("rough"), bool):
            out.append(r)
        if kind == "M" and r.get("category") in ("urgent", "threat", "normal"):
            out.append(r)
    for i, r in enumerate(out):
        r["id"] = i
    return out


def strip():
    for kind in ("S", "M"):
        b = [{"id": r["id"], "text": r["text"]} for r in rows(kind)]
        random.Random(3).shuffle(b)
        (GEN / f"blind_{kind}.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in b) + "\n", encoding="utf-8")
        print(kind, len(b), Counter(r.get("type") for r in rows(kind)))


def leaks(text, train_g):
    g = grams(text)
    return any(len(g & e) / len(g | e) > 0.5 or len(g & e) / len(g) > 0.7 or len(g & e) / len(e) > 0.7 for e in train_g)


def merge():
    train_g = [grams(x["text"]) for x in train.load_items()]
    train_g = [e for e in train_g if len(e) >= 4]  # 아주 짧은 학습 문장(“네”)은 포함률 비교에서 뺀다
    out, report = {}, []
    for kind, key in (("S", "rough"), ("M", "category")):
        lab = {d["id"]: d for d in read_jsonl([GEN / f"label_{kind}.jsonl"]) if "id" in d}
        rs = rows(kind)
        agree = [r for r in rs if r["id"] in lab and lab[r["id"]].get(key) == r[key]]
        seen, keep, leaked = set(), [], 0
        for r in agree:
            k = "".join(r["text"].split())
            if k in seen:
                continue
            seen.add(k)
            if leaks(r["text"], train_g):
                leaked += 1
                continue
            keep.append({"text": r["text"].strip(), key: r[key], "type": r.get("type")})
        out["sentences" if kind == "S" else "messages"] = keep
        report.append(f"{kind}: 생성 {len(rs)} · 라벨 일치 {len(agree)} · 학습 데이터와 비슷해서 뺌 {leaked} · 최종 {len(keep)} "
                      f"{Counter(x[key] for x in keep)}")
    out["_note"] = ("Claude Sonnet 서브 에이전트가 만든 합성 시험셋 (11.04). 라벨을 지운 문장에 다른 에이전트가 다시 라벨을 붙여 일치한 것만, "
                    "학습 데이터와 비슷한 것은 뺐다. 학습 · 기준값 고르기에 안 쓴다. 사람이 쓴 문장이 아니므로 발표 땐 '합성 시험셋'이라고 밝힌다.")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(report), "→", OUT)


if __name__ == "__main__":
    {"strip": strip, "merge": merge}[sys.argv[1]]()
