"""AI 판단 평가 — 키워드 / 로컬 모델 / 둘 다를 같은 평가셋으로 채점해 ml/results.md에 쓴다.

실행 (레포 루트에서): backend/.venv/Scripts/python ml/evaluate.py
로컬 모델(torch · transformers)이 있어야 local · both 줄이 의미가 있다. 요약 예시는 backend/.env 키가 있을 때만.
"""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai import analyzer as ai  # noqa: E402

data = json.loads((ROOT / "ml" / "eval_set.json").read_text(encoding="utf-8"))
S, M = data["sentences"], data["messages"]
texts, gold = [s["text"] for s in S], [s["rough"] for s in S]


def score(pred):
    tp = sum(p and g for p, g in zip(pred, gold))
    fp = sum(p and not g for p, g in zip(pred, gold))
    fn = sum(g and not p for p, g in zip(pred, gold))
    prec, rec = tp / (tp + fp or 1), tp / (tp + fn or 1)
    return prec, rec, 2 * prec * rec / (prec + rec or 1), fp / (len(gold) - sum(gold))


def by_group(pred):
    groups = {}
    for s, p in zip(S, pred):
        ok = groups.setdefault(s["group"], [0, 0])
        ok[0] += p == s["rough"]
        ok[1] += 1
    return " · ".join(f"{g} {a}/{n}" for g, (a, n) in groups.items())


out = ["# AI 판단 평가 결과", "",
       f"평가셋 `ml/eval_set.json` — 문장 {len(S)}개(거친 {sum(gold)} · 괜찮은 {len(gold) - sum(gold)}), 메시지 {len(M)}개. "
       f"로컬 모델 `{ai.LOCAL_NAME}` {'켜짐' if ai._load() else '꺼짐'}.", "",
       "⚠️ 키워드 사전과 평가셋을 같은 사람이 만들어 **키워드 점수는 실제보다 높게 나올 수 있다.** 팀원이 새 문장을 더하면 더 공정해진다.", "",
       "## 1. 거친 표현 판단 (문장 단위)", "",
       "| 방식 | 정밀도 | 재현율 | F1 | 과잉 가림률 | 종류별 맞힌 수 |", "|---|---|---|---|---|---|"]
for mode, label in (("keyword", "키워드만"), ("local", "로컬 모델만"), ("both", "로컬 모델 + 키워드 (앱)")):
    pred = ai.rough_flags(texts, mode)
    p, r, f, over = score(pred)
    out.append(f"| {label} | {p:.2f} | {r:.2f} | {f:.2f} | {over:.2f} | {by_group(pred)} |")

sc = ai.toxic_scores(texts)
if sc:
    out += ["", "로컬 모델 기준값(`TOXIC_MIN`)에 따른 변화 — 앱은 0.3을 쓴다.", "",
            "| 기준값 | 정밀도 | 재현율 | F1 | 과잉 가림률 |", "|---|---|---|---|---|"]
    for th in (0.2, 0.3, 0.4, 0.5, 0.6):
        p, r, f, over = score([x >= th for x in sc])
        out.append(f"| {th} | {p:.2f} | {r:.2f} | {f:.2f} | {over:.2f} |")

# 2. 메시지 분류 (긴급 · 위협 · 일반) — 키워드만 vs 키워드 + API 판단 (앱)
runs = [("키워드만", [ai.analyze(m["text"], use_api=False)["category"] for m in M])]
if ai.writer_name():
    runs.append((f"키워드 + API ({ai.writer_name()})", [ai.analyze(m["text"])["category"] for m in M]))
out += ["", "## 2. 메시지 분류 (긴급 · 위협 · 일반)", "", "| 방식 | 분류 | 재현율 | 놓친 메시지 |", "|---|---|---|---|"]
for name, pred in runs:
    for cat, label in (("urgent", "긴급"), ("threat", "위협"), ("normal", "일반")):
        idx = [i for i, m in enumerate(M) if m["category"] == cat]
        miss = [f"“{M[i]['text']}” → {pred[i]}" for i in idx if pred[i] != cat]
        out.append(f"| {name} | {label} | {(len(idx) - len(miss)) / len(idx):.2f} | {'<br>'.join(miss) or '—'} |")

# 3. 속도 · 요약 예시
t = time.perf_counter(); ai.rough_flags(texts[:10]); judge_ms = (time.perf_counter() - t) * 1000 / 10
out += ["", "## 3. 속도", "", f"- 로컬 판단: 문장 하나에 약 {judge_ms:.0f}ms (CPU)"]
if ai.writer_name():
    samples = [m["text"] for m in M if m["category"] != "urgent"][:6]
    times, rows = [], []
    for s in samples:
        t = time.perf_counter(); r = ai.analyze(s); times.append(time.perf_counter() - t)
        rows.append(f"| {s} | {r['summary']} |")
    out.append(f"- 분석 전체(판단 + API 요약): 평균 {statistics.mean(times):.1f}초 · 최대 {max(times):.1f}초 ({ai.writer_name()}, {len(samples)}건)")
    t = time.perf_counter(); p = ai.precheck(M[21]["text"]); pre = time.perf_counter() - t
    out.append(f"- 보내기 전 검사(판단 + API 제안 문장): {pre:.1f}초 — 5초 규칙 {'통과' if pre < 5 else '초과'}")
    out += ["", "## 4. 요약 예시 (API)", "", "| 학부모 메시지 | 교사가 보는 요약 |", "|---|---|", *rows,
            "", f"보내기 전 검사 제안 문장 — “{M[21]['text']}” → “{p['suggestions'][0] if p['suggestions'] else '없음'}”"]

(ROOT / "ml" / "results.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
