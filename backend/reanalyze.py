"""이미 받은 메시지의 AI 분석을 지금 판단기로 다시 만든다 — 원문(messages)은 건드리지 않고 analyses만 갱신.

실행 (backend에서): .venv/Scripts/python reanalyze.py           (바뀌는 것만 보여 줌)
                    .venv/Scripts/python reanalyze.py --write   (실제로 저장)
분류(긴급 · 위협 · 일반)가 바뀌는 메시지는 알림 · 학교 이관이 얽혀 있어 저장하지 않고 목록만 보여 준다.
"""
import json
import sys

from app.ai.analyzer import analyze
from app.api.main import now, row, rows, tx

WRITE = "--write" in sys.argv
ms = rows("""SELECT m.id, m.original_text, m.category, a.request_summary, a.threat_reason, cm.child_name, p.name parent_name, t.name teacher_name
             FROM messages m JOIN analyses a ON a.message_id = m.id JOIN users p ON p.id = m.parent_id JOIN users t ON t.id = m.teacher_id
             LEFT JOIN class_members cm ON cm.user_id = m.parent_id AND cm.class_id = m.class_id""")
changed, skipped = 0, []
for m in ms:
    r = analyze(m["original_text"], [m["child_name"], m["parent_name"], m["teacher_name"]])
    if r["category"] != m["category"]:
        skipped.append((m["id"], m["category"], r["category"], m["original_text"][:40]))
        continue
    if (r["request_summary"], r["threat_reason"]) == (m["request_summary"], m["threat_reason"]):
        continue
    changed += 1
    print(f"#{m['id']} {m['category']}\n  요청 {m['request_summary']} → {r['request_summary']}\n  이유 {m['threat_reason']} → {r['threat_reason']}")
    if WRITE:
        with tx() as c:
            c.execute("""UPDATE analyses SET summary = ?, requests = ?, request_summary = ?, threat_reason = ?, masked_spans = ?, masked_count = ?,
                         model = ?, analyzed_at = ? WHERE message_id = ?""",
                      (r["summary"], json.dumps(r["requests"], ensure_ascii=False), r["request_summary"], r["threat_reason"],
                       json.dumps(r["masked_spans"]), len(r["masked_spans"]), r["model"], now(), m["id"]))
print(f"\n바뀜 {changed}건{' (저장함)' if WRITE else ' (저장 안 함 · --write로 저장)'} · 분류가 달라져 건너뜀 {len(skipped)}건")
for s in skipped:
    print("  건너뜀", s)
