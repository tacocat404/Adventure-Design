"""발표용 실험 두 가지 — 결과는 ml/experiments.md · ml/experiments.json

1) 학습 곡선: 학습 문장을 500 · 1000 · 2000 · 전체로 늘리며 같은 평가셋 점수를 잰다 (전체 = ml/models/judge, 먼저 train.py)
2) 구성 요소별 기여(ablation): 지금 모델에서 키워드 · BERT · kNN · 스태킹을 하나씩 더해 가며 점수를 잰다

실행 (레포 루트): backend/.venv/Scripts/python ml/experiments.py          (둘 다)
                 backend/.venv/Scripts/python ml/experiments.py ablation (2만, 1분)
모두 API 없이 로컬 판단만 잰다. 평가셋은 학습에 쓰지 않는다. GPU가 있으면 학습 곡선이 빨라진다 (Colab).
"""
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))
from app.ai import analyzer as ai  # noqa: E402
from app.ai.judge import Judge  # noqa: E402

import train  # noqa: E402

EV = json.loads((ROOT / "ml" / "eval_set.json").read_text(encoding="utf-8"))
S, M = EV["sentences"], EV["messages"]
SIZES = [500, 1000, 2000]


def score():
    """지금 켜져 있는 판단기로 평가셋 점수 (앱의 analyze와 같은 경로, API 없이)."""
    pred = ai.rough_flags([s["text"] for s in S], "judge" if ai._judge_model else "both")
    gold = [s["rough"] for s in S]
    tp = sum(p and g for p, g in zip(pred, gold)); fp = sum(p and not g for p, g in zip(pred, gold))
    fn = sum(g and not p for p, g in zip(pred, gold))
    cats = [ai.analyze(m["text"], use_api=False)["category"] for m in M]
    rec = lambda c: sum(p == c for p, m in zip(cats, M) if m["category"] == c) / sum(m["category"] == c for m in M)
    false_alarm = sum(p != "normal" for p, m in zip(cats, M) if m["category"] == "normal")
    return {"rough_f1": round(2 * tp / max(2 * tp + fp + fn, 1), 3), "over_mask": round(fp / (len(gold) - sum(gold)), 3),
            "threat_recall": round(rec("threat"), 2), "urgent_recall": round(rec("urgent"), 2), "false_alarm": false_alarm}


def use(judge):
    ai._judge_model = judge


def learning_curve():
    rows, tmp = [], Path(tempfile.mkdtemp())
    try:
        for n in SIZES:
            t = time.time()
            d = tmp / f"lc_{n}"
            train.main(out=d, limit=n, quiet=True)
            use(Judge(d, quantize=False)); r = score()
            rows.append({"train": n, **r, "sec": round(time.time() - t)})
            print(rows[-1], flush=True)
            shutil.rmtree(d, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    j = Judge(train.OUT, quantize=False)
    n_all = json.loads((train.OUT / "train_log.json").read_text(encoding="utf-8")).get("train")
    use(j); rows.append({"train": n_all or "전체", **score()})
    print(rows[-1], flush=True)
    return rows


def ablation():
    j = Judge(train.OUT, quantize=False)
    full_stack, full_cfg = j.stack, j.cfg
    rows = []
    # 이전 앱 · 키워드만: 증류 판단기를 끄고 예전 경로로
    use(False); ai._model = False
    rows.append({"구성": "① 키워드만", **score()})
    ai._model = None
    rows.append({"구성": "이전 앱 (kor_unsmile + 키워드)", **score()})
    # 하나씩: 스태킹 대신 그 점수만 0.5로 자른다
    half = {l: {**full_cfg[l], "th": 0.5} for l in full_cfg}
    for name, col in (("② BERT만", 1), ("③ kNN만", 2)):
        j.stack, j.cfg = (lambda f, c=col: f[:, :, c]), half
        use(j); rows.append({"구성": name, **score()})
    j.stack, j.cfg = (lambda f: f[:, :, 1:].mean(-1)), half
    use(j); rows.append({"구성": "②+③ 평균", **score()})
    j.stack, j.cfg = full_stack, full_cfg
    use(j); rows.append({"구성": "①+②+③ 스태킹 (지금 앱)", **score()})
    for r in rows:
        print(r, flush=True)
    return rows


def table(rows, first):
    keys = [first, "rough_f1", "over_mask", "threat_recall", "urgent_recall", "false_alarm"]
    head = {first: first, "rough_f1": "거친 표현 F1", "over_mask": "과잉 가림률", "threat_recall": "위협 재현율",
            "urgent_recall": "긴급 재현율", "false_alarm": "일반 오경보 /10"}
    return ["| " + " | ".join(head[k] for k in keys) + " |", "|" + "---|" * len(keys),
            *["| " + " | ".join(str(r[k]) for k in keys) + " |" for r in rows]]


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out_json = ROOT / "ml" / "experiments.json"
    res = json.loads(out_json.read_text(encoding="utf-8")) if out_json.exists() else {}
    if which in ("all", "ablation"):
        res["ablation"] = ablation()
    if which in ("all", "curve"):
        res["learning_curve"] = learning_curve()
    out_json.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# 발표용 실험", "", "평가셋 `ml/eval_set.json` (문장 60 · 메시지 30, 학습에 안 씀) · **API 없이 로컬 판단만** · 위협 · 긴급 메시지 각 10개라 한 개 = 0.10", ""]
    if "ablation" in res:
        md += ["## 구성 요소별 기여", "", "②③만 쓸 때는 기준값 0.5. 스태킹은 검증셋(학습 데이터에서 뗀 15%)으로 가중치 · 기준값을 맞춘 것.", "",
               *table(res["ablation"], "구성"), ""]
    if "learning_curve" in res:
        md += ["## 학습 곡선", "", "검증셋은 고정, 학습 문장만 늘린다. 문장 수는 구절로 늘리기 전 고유 문장.", "",
               *table(res["learning_curve"], "train"), ""]
    (ROOT / "ml" / "experiments.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
