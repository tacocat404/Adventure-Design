"""큰 합성 시험셋(ml/eval_big.json)으로 이전 앱 · 지금 앱을 재고, 95% 신뢰구간(Wilson)까지 → ml/results_big.md

실행 (레포 루트): backend/.venv/Scripts/python ml/evaluate_big.py          (API 포함, 약 10분)
                 backend/.venv/Scripts/python ml/evaluate_big.py --local  (로컬만, 약 2분)
"""
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai import analyzer as ai  # noqa: E402

EV = json.loads((ROOT / "ml" / "eval_big.json").read_text(encoding="utf-8"))
S, M = EV["sentences"], EV["messages"]
LOCAL = "--local" in sys.argv


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt(k, n):
    lo, hi = wilson(k, n)
    return f"{k / n:.2f} ({lo:.2f}~{hi:.2f})" if n else "—"


def set_mode(mode):
    """keyword · old(kor_unsmile + 키워드) · new(증류 판단기)"""
    ai._judge_model = None if mode == "new" else False
    ai._model = False if mode == "keyword" else None
    if mode == "new":
        ai.load_judge()


def sentences(mode):
    set_mode(mode)
    pred = ai.rough_flags([s["text"] for s in S], "judge" if mode == "new" else ("keyword" if mode == "keyword" else "both"))
    gold = [s["rough"] for s in S]
    tp = sum(p and g for p, g in zip(pred, gold)); fp = sum(p and not g for p, g in zip(pred, gold))
    fn = sum(g and not p for p, g in zip(pred, gold)); pos, neg = sum(gold), len(gold) - sum(gold)
    f1 = 2 * tp / max(2 * tp + fp + fn, 1)
    miss = [s["text"] for s, p in zip(S, pred) if s["rough"] and not p]
    over = [s["text"] for s, p in zip(S, pred) if p and not s["rough"]]
    return {"F1": f"{f1:.3f}", "재현율": fmt(tp, pos), "정밀도": fmt(tp, tp + fp), "과잉 가림률": fmt(fp, neg)}, miss, over


def messages(mode, use_api):
    set_mode(mode)
    with ThreadPoolExecutor(6 if use_api else 4) as ex:
        cats = list(ex.map(lambda m: ai.analyze(m["text"], use_api=use_api)["category"], M))
    out, wrong = {}, []
    for c, label in (("urgent", "긴급 재현율"), ("threat", "위협 재현율")):
        idx = [i for i, m in enumerate(M) if m["category"] == c]
        out[label] = fmt(sum(cats[i] == c for i in idx), len(idx))
    norm = [i for i, m in enumerate(M) if m["category"] == "normal"]
    out["일반 오경보율"] = fmt(sum(cats[i] != "normal" for i in norm), len(norm))
    out["정확도"] = fmt(sum(c == m["category"] for c, m in zip(cats, M)), len(M))
    wrong = [(m["text"], m["category"], c) for m, c in zip(M, cats) if c != m["category"]]
    return out, wrong


def table(rows, cols):
    return ["| 방식 | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols),
            *[f"| {name} | " + " | ".join(r[c] for c in cols) + " |" for name, r in rows]]


def main():
    t0 = time.time()
    md = ["# 큰 합성 시험셋 평가", "", f"`ml/eval_big.json` — 문장 {len(S)}개(거친 {sum(s['rough'] for s in S)}) · 메시지 {len(M)}개 "
          f"(긴급 {sum(m['category'] == 'urgent' for m in M)} · 위협 {sum(m['category'] == 'threat' for m in M)} · "
          f"일반 {sum(m['category'] == 'normal' for m in M)}). 학습에 안 씀. 괄호는 95% 신뢰구간(Wilson).", "",
          "⚠️ Claude Sonnet이 만든 **합성** 시험셋이다. 학습 데이터도 Claude가 만들어 말투가 비슷하므로, 실제 학부모 메시지에서는 더 낮게 나올 수 있다. "
          "사람이 쓴 시험 문제(`ml/review/시험문제_양식.csv`)로 다시 재야 한다.", "", "## 1. 거친 표현 (문장)", ""]
    srows, fails = [], {}
    for mode, name in (("keyword", "키워드만"), ("old", "이전 앱 (kor_unsmile + 키워드)"), ("new", "지금 앱 (증류 판단기)")):
        r, miss, over = sentences(mode)
        srows.append((name, r)); fails[mode] = (miss, over)
        print(name, r, flush=True)
    md += table(srows, ["F1", "재현율", "정밀도", "과잉 가림률"])
    md += ["", "## 2. 메시지 분류", ""]
    mrows, mwrong = [], {}
    runs = [("keyword", False, "키워드만"), ("old", False, "이전 앱 · 로컬만"), ("new", False, "지금 앱 · 로컬만")]
    if not LOCAL and ai.writer_name():
        runs += [("old", True, f"이전 앱 + API ({ai.writer_name()})"), ("new", True, "지금 앱 + API")]
    for mode, api, name in runs:
        r, wrong = messages(mode, api)
        mrows.append((name, r)); mwrong[name] = wrong
        print(name, r, flush=True)
    md += table(mrows, ["긴급 재현율", "위협 재현율", "일반 오경보율", "정확도"])
    miss, over = fails["new"]
    md += ["", "## 3. 지금 앱이 틀린 예", "", f"### 거친 표현을 놓침 ({len(miss)})", "", *[f"- {t}" for t in miss[:15]],
           "", f"### 괜찮은 문장을 가림 ({len(over)})", "", *[f"- {t}" for t in over[:15]]]
    last = mrows[-1][0]
    md += ["", f"### 메시지 분류가 틀림 — {last} ({len(mwrong[last])})", "",
           *[f"- {t} → 정답 {g} · 판단 {p}" for t, g, p in mwrong[last][:20]], "", f"(평가 {time.time() - t0:.0f}초)"]
    (ROOT / "ml" / "results_big.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
