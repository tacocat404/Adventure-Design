"""증류 학습 — kor_unsmile을 교사 LLM 라벨(ml/data/train.json)로 파인튜닝하고, kNN 뱅크 · 스태킹 가중치까지 만든다.

실행 (레포 루트): backend/.venv/Scripts/python ml/train.py   (GPU가 있으면 GPU로 · Colab: ml/colab_train.ipynb)
결과: ml/models/judge/ (모델 · 토크나이저 · bank.npz · stack.json · train_log.json)
평가셋(ml/eval_set.json)은 여기서 한 번도 쓰지 않는다. 기준값은 학습 데이터에서 떼어 둔 검증셋으로만 고른다.
"""
import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai import analyzer as ai  # noqa: E402
from app.ai.judge import LABELS, Judge  # noqa: E402

OUT = ROOT / "ml" / "models" / "judge"
EPOCHS, BATCH, LR, MAX_LEN, SEED = 4, 16, 3e-5, 64, 0
# 기준값: 오경보율(FPR)을 넘지 않는 선에서 위협 · 긴급은 재현율 최대, 거친 표현은 F0.5 최대.
# 위협 · 긴급은 API가 한 번 더 보므로(더 심각한 쪽을 따름) 로컬은 오경보를 먼저 막는다.
# (처음엔 '재현율 0.95 이상'으로 골랐더니 기준값이 0.02까지 내려가 '고소한 냄새'도 위협이 됐다 — stress_test 11.04)
FPR_MAX = {"rough": 0.05, "threat": 0.03, "urgent": 0.03}


def label_vec(x):
    # 위협 문장은 화면에서도 가린다 (지금 앱과 같은 규칙)
    return [float(x["rough"] or x["category"] == "threat"), float(x["category"] == "threat"), float(x["category"] == "urgent")]


def fit_logreg(X, y, steps=3000, lr=0.5, l2=1e-3):
    w, b = np.zeros(X.shape[1]), 0.0
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = p - y
        w -= lr * (X.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return w, b


def pick_threshold(q, y, lab):
    """오경보율 상한 안에서 가장 좋은 점수(위협 · 긴급은 재현율, 거침은 F1)를 내는 기준값들 가운데 '가운데'를 고른다.
    합성 검증셋은 쉬워서 점수가 0.02 아니면 0.9로 갈린다 — 같은 성적이 나는 구간이 넓은데, 그 끝(0.82)을 고르면
    실제 문장(평가셋)에서 긴급 재현율이 0.40까지 떨어졌다 (11.04). 구간의 가운데(로짓 기준)가 분포가 바뀌어도 가장 덜 흔들린다."""
    scored = []
    for th in sorted(set(np.round(q, 3)) | {0.5}):
        pred = q >= th
        tp, fp = (pred & (y == 1)).sum(), (pred & (y == 0)).sum()
        fn, tn = (~pred & (y == 1)).sum(), (~pred & (y == 0)).sum()
        rec, fpr = tp / max(tp + fn, 1), fp / max(fp + tn, 1)
        f05 = 1.25 * tp / max(1.25 * tp + 0.25 * fn + fp, 1)  # 거침은 F0.5: 과잉 가림을 놓침보다 무겁게 (교사가 원문 보기로 확인 가능)
        if fpr <= FPR_MAX[lab]:
            scored.append((round(float(f05 if lab == "rough" else rec), 3), float(th)))
    if not scored:
        return 0.9
    top = max(k for k, _ in scored)
    ths = [min(max(t, 1e-3), 1 - 1e-3) for k, t in scored if k == top]
    lo, hi = np.log(min(ths) / (1 - min(ths))), np.log(max(ths) / (1 - max(ths)))
    return round(float(1 / (1 + np.exp(-(lo + hi) / 2))), 3)


def split_clauses(items):
    """평범한 문장(안 거칠고 일반)은 구절로도 나눠 더한다 — 앱은 구절 단위로 판단하기 때문.
    LLM이 쓴 평범한 문장은 '선생님 안녕하세요 ○○ 엄마예요'로 길게 시작해, 모델이 '짧고 무뚝뚝하면 거침'이라는
    지름길을 배웠다 ('내일은 할머니 댁에 가서 결석할 것 같아요.' → 위협 0.99, 11.04)."""
    out = list(items)
    for x in items:
        if x["rough"] or x["category"] != "normal":
            continue
        cl = [c for _, _, c in ai._clauses(x["text"])]
        if len(cl) > 1:
            out += [{**x, "text": c, "type": x["type"] + "_구절"} for c in cl if len(ai.HANGUL.findall(c)) >= 4]
    return out


def load_items():
    """학습 데이터 전체. reviewed.json(팀원 두 명이 검수 · 가장 우선) + train.json(API LLM) + short.json(짧은 긴급 · 위협)
    + hand.json(직접 쓴 위협) + claude.json(Sonnet 에이전트). 같은 문장이 여러 파일에 있으면 앞 파일(사람 검수) 라벨을 쓴다."""
    out, seen = [], set()
    for f in ("reviewed.json", "train.json", "short.json", "hand.json", "claude.json", "claude_F.json"):
        p = ROOT / "ml" / "data" / f
        for x in (json.loads(p.read_text(encoding="utf-8"))["items"] if p.exists() else []):
            key = "".join(x["text"].split())
            if key not in seen:
                seen.add(key)
                out.append(x)
    return out


def split(items):
    """검증셋을 먼저 떼고(고정), 나머지를 학습. 학습 곡선 실험에서도 같은 검증셋을 쓴다."""
    items = list(items)
    random.Random(SEED).shuffle(items)
    n_val = max(60, len(items) * 15 // 100)
    return items[:n_val], items[n_val:]


def main(out=OUT, limit=None, quiet=False):
    """limit: 학습 문장 수(구절로 늘리기 전 고유 문장)를 이만큼만 쓴다 — 학습 곡선 실험용."""
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    val0, tr0 = split(load_items())
    tr0 = tr0[:limit] if limit else tr0
    val, tr = split_clauses(val0), split_clauses(tr0)  # 나눈 뒤에 늘린다: 같은 문장 조각이 학습 · 검증에 함께 들어가지 않게
    print(f"학습 {len(tr0)}문장(구절 포함 {len(tr)}) · 검증 {len(val)} · {dev}", flush=True)

    if "--stack-only" in sys.argv and out == OUT:  # BERT는 그대로 두고 스태킹 · 기준값만 다시
        return fit_stack(val, out)
    tok = AutoTokenizer.from_pretrained(ai.LOCAL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        ai.LOCAL_NAME, num_labels=3, problem_type="multi_label_classification", ignore_mismatched_sizes=True,
        id2label=dict(enumerate(LABELS)), label2id={l: i for i, l in enumerate(LABELS)}).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    steps = EPOCHS * ((len(tr) + BATCH - 1) // BATCH)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / (0.1 * steps)) * max(0.0, 1 - s / steps))
    # 위협 · 긴급은 수가 적으니 더 무겁게
    ys = np.array([label_vec(x) for x in tr])
    pos_w = torch.tensor(np.clip((len(ys) - ys.sum(0)) / np.maximum(ys.sum(0), 1), 1, 5), dtype=torch.float32, device=dev)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_w)

    log, t0 = [], time.time()
    for ep in range(EPOCHS):
        model.train()
        random.shuffle(tr)
        total = 0.0
        for i in range(0, len(tr), BATCH):
            b = tr[i:i + BATCH]
            enc = tok([x["text"] for x in b], return_tensors="pt", padding=True, truncation=True, max_length=MAX_LEN).to(dev)
            loss = loss_fn(model(**enc).logits, torch.tensor([label_vec(x) for x in b], device=dev))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); opt.zero_grad()
            total += loss.item() * len(b)
            if not quiet and (i // BATCH) % 50 == 0:
                print(f"  epoch {ep + 1} · {i}/{len(tr)} · {time.time() - t0:.0f}초", flush=True)
        log.append({"epoch": ep + 1, "loss": round(total / len(tr), 4), "sec": round(time.time() - t0)})
        print(log[-1])

    out.mkdir(parents=True, exist_ok=True)
    model.to("cpu").save_pretrained(out)  # 앱은 CPU에서 INT8로 돌린다
    tok.save_pretrained(out)
    del model
    if dev == "cuda":
        torch.cuda.empty_cache()

    # kNN 뱅크 = 학습 문장 (검증 문장은 넣지 않는다 — 스태킹이 실제처럼 '처음 보는 문장'으로 배우게)
    np.savez(out / "bank.npz", emb=np.zeros((1, 768), np.float16), y=np.zeros((1, 3), np.float16), type=np.array(["-"]))
    (out / "stack.json").write_text(json.dumps({l: {"w": [0, 1, 0], "b": 0, "th": 0.5} for l in LABELS}), encoding="utf-8")
    j = Judge(out, quantize=False)
    embs = [j.encode([x["text"] for x in tr[i:i + 64]])[1] for i in range(0, len(tr), 64)]
    np.savez(out / "bank.npz", emb=np.concatenate(embs).astype(np.float16), y=np.array([label_vec(x) for x in tr], np.float16),
             type=np.array([x["type"] for x in tr]))

    fit_stack(val, out, log, n_train=len(tr0))


def fit_stack(val, out=OUT, log=None, n_train=None):
    """스태킹: 검증셋으로 라벨마다 로지스틱 회귀 + 기준값."""
    j = Judge(out, quantize=False)  # 앱과 똑같이 fp32 (INT8은 배치에 따라 점수가 흔들려 뺐다)
    vt = [x["text"] for x in val]
    f = np.concatenate([j.features(vt[i:i + 64], [ai.kw_vec(s) for s in vt[i:i + 64]])[0] for i in range(0, len(vt), 64)])
    yv = np.array([label_vec(x) for x in val])
    cfg = {}
    for k, lab in enumerate(LABELS):
        w, b = fit_logreg(f[:, k, :], yv[:, k])
        q = 1 / (1 + np.exp(-(f[:, k, :] @ w + b)))
        th = pick_threshold(q, yv[:, k].astype(int), lab)
        if lab != "rough":
            # 키워드 · kNN만으로는 위협 · 긴급이 되지 않게 — BERT도 그렇다고 봐야 넘는다.
            # 키워드만: '고소한 냄새', '찾아가는 음악회'가 위협이 됐다. kNN만: 시연 문장 '짝이랑 안 맞아서 매일 울면서 와요'가
            # BERT 0.15인데 이웃이 긴급 문장이라 kNN 0.86 → 긴급이 됐다 (stress_test · 자체 검사 11.04)
            th = max(th, round(float(1 / (1 + np.exp(-(b + w[0] + w[2])))) + 0.02, 3))
        cfg[lab] = {"w": [round(float(v), 4) for v in w], "b": round(float(b), 4), "th": th}
    (out / "stack.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    path = out / "train_log.json"
    prev = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    path.write_text(json.dumps({**prev, "val": len(val), "stack": cfg, "base": ai.LOCAL_NAME, **({"epochs": log} if log else {}),
                               **({"train": n_train} if n_train else {})},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print("스태킹", json.dumps(cfg, ensure_ascii=False))


if __name__ == "__main__":
    main()
