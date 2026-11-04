"""서브 에이전트(Claude Sonnet)가 만든 문장을 교차 검사해 학습 데이터로 합친다.

1) 생성: ml/data/gen/{A..E}_*.jsonl  ({"text", "rough", "category", "type"})
2) strip:  python ml/import_gen.py strip  → ml/data/gen/blind_*.jsonl  (라벨을 지운 {"id", "text"}, 200줄씩)
           다른 에이전트가 이걸 보고 처음부터 라벨을 붙여 ml/data/gen/label_*.jsonl ({"id", "rough", "category"})로 쓴다
3) merge:  python ml/import_gen.py merge  → ml/data/claude.json
           두 라벨이 일치하고, 기존 학습 데이터 · 평가셋과 비슷하지 않은 문장만 남긴다
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "ml" / "data" / "gen"
OUT = ROOT / "ml" / "data" / "claude.json"
CHUNK = 200


def read_jsonl(paths):
    rows = []
    for p in paths:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip().strip(",")
            if line.startswith("{"):
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def generated():
    rows = read_jsonl(sorted(p for p in GEN.glob("[A-E]_*.jsonl")))
    rows = [r for r in rows if isinstance(r.get("text"), str) and r["text"].strip()
            and isinstance(r.get("rough"), bool) and r.get("category") in ("urgent", "threat", "normal")]
    for i, r in enumerate(rows):
        r["id"] = i
    return rows


def grams(s):
    s = "".join(s.split())
    return {s[i:i + 3] for i in range(len(s) - 2)} or {s}


def strip():
    rows = generated()
    blind = [{"id": r["id"], "text": r["text"]} for r in rows]
    random.Random(1).shuffle(blind)  # 같은 유형끼리 몰려 있으면 라벨러가 패턴으로 찍는다
    for old in GEN.glob("blind_*.jsonl"):
        old.unlink()
    for k in range(0, len(blind), CHUNK):
        (GEN / f"blind_{k // CHUNK + 1}.jsonl").write_text(
            "\n".join(json.dumps(b, ensure_ascii=False) for b in blind[k:k + CHUNK]) + "\n", encoding="utf-8")
    print(f"생성 {len(rows)}줄 → blind_*.jsonl {(len(blind) + CHUNK - 1) // CHUNK}개", Counter(r["type"] for r in rows))


def merge():
    rows = {r["id"]: r for r in generated()}
    labels = {d["id"]: d for d in read_jsonl(sorted(GEN.glob("label_*.jsonl"))) if "id" in d}
    agree = [r for i, r in rows.items() if i in labels
             and bool(labels[i].get("rough")) == r["rough"] and labels[i].get("category") == r["category"]]
    print(f"생성 {len(rows)} · 라벨 받음 {len(labels)} · 두 라벨 일치 {len(agree)}")
    miss = Counter((r["type"], labels[i].get("category"), labels[i].get("rough")) for i, r in rows.items()
                   if i in labels and r not in agree)
    print("불일치 상위:", miss.most_common(8))

    old = [x["text"] for f in ("train.json", "short.json", "hand.json") if (ROOT / "ml" / "data" / f).exists()
           for x in json.loads((ROOT / "ml" / "data" / f).read_text(encoding="utf-8"))["items"]]
    ev = json.loads((ROOT / "ml" / "eval_set.json").read_text(encoding="utf-8"))
    ev_g = [grams(s["text"]) for s in ev["sentences"]] + [grams(m["text"]) for m in ev["messages"]]
    seen = {"".join(t.split()) for t in old}
    keep, near_eval = [], 0
    for r in agree:
        key, g = "".join(r["text"].split()), grams(r["text"])
        if key in seen:
            continue
        # 전체가 비슷하거나(자카드), 평가셋 문장 안에 거의 그대로 들어 있는 조각이면(포함률) 뺀다
        # 예: 생성 “그땐 저도 몰라요” ⊂ 평가셋 “우리 애 한 번만 더 혼내면 그땐 저도 몰라요.”
        if any(len(g & e) / len(g | e) > 0.5 or len(g & e) / len(g) > 0.7 for e in ev_g):
            near_eval += 1
            continue
        seen.add(key)
        keep.append({"text": r["text"].strip(), "rough": r["rough"], "category": r["category"], "type": r["type"]})
    OUT.write_text(json.dumps({"_note": "Claude Sonnet 서브 에이전트가 만들고, 라벨을 지운 문장에 다른 에이전트가 다시 라벨을 붙여 "
                                        "두 번 다 맞은 것만. 실제 학부모 메시지 아님. 사람 검수 전.", "items": keep},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"평가셋과 비슷해서 뺌 {near_eval} · 최종 {len(keep)} → {OUT}", Counter(x["type"] for x in keep))


if __name__ == "__main__":
    {"strip": strip, "merge": merge}[sys.argv[1]]()
