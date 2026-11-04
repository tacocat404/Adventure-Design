"""담임 피드백 → 라벨 붙일 문장 목록 (능동학습 큐).

실행 (레포 루트): backend/.venv/Scripts/python ml/export_feedback.py
결과: ml/data/feedback_queue.json — 사람이 rough · category를 확인해 ml/data/train.json에 더한 뒤 ml/train.py를 다시 돌린다.
피드백이 달린 메시지의 구절 가운데, 판단기 점수가 기준값 근처(애매한 것)부터 위에 둔다. 이름은 [이름]으로 바꿔 내보낸다.
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai import analyzer as ai  # noqa: E402

DB = ROOT / "backend" / "cushion.db"
OUT = ROOT / "ml" / "data" / "feedback_queue.json"


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    have = c.execute("SELECT 1 FROM sqlite_master WHERE name = 'ai_feedback'").fetchone()
    fb = c.execute("""SELECT f.id, f.kind, f.ai_category, f.note, m.original_text,
                      (SELECT GROUP_CONCAT(cm.child_name) FROM class_members cm WHERE cm.class_id = m.class_id AND cm.child_name IS NOT NULL) kids,
                      (SELECT GROUP_CONCAT(u.name) FROM users u WHERE u.id IN (m.parent_id, m.teacher_id)) adults
                      FROM ai_feedback f JOIN messages m ON m.id = f.message_id WHERE f.used_at IS NULL""").fetchall() if have else []
    j = ai.load_judge()
    queue = []
    for f in fb:
        text = f["original_text"]
        for n in sorted({x for x in ((f["kids"] or "") + "," + (f["adults"] or "")).split(",") if x}, key=len, reverse=True):
            text = text.replace(n, "[이름]")
        cl = [s for _, _, s in ai._clauses(text)] or [text]
        if j:
            _, q, _ = j.predict(cl, [ai.kw_vec(s) for s in cl])
            th = [j.cfg[l]["th"] for l in ("rough", "threat", "urgent")]
            doubt = [float(min(abs(q[i, k] - th[k]) for k in range(3))) for i in range(len(cl))]
        else:
            doubt = [0.0] * len(cl)
        for s, d in zip(cl, doubt):
            queue.append({"feedback_id": f["id"], "kind": f["kind"], "ai_category": f["ai_category"], "text": s,
                          "doubt": round(d, 3), "rough": None, "category": None})
    queue.sort(key=lambda x: x["doubt"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"_note": "rough · category를 사람이 채운 뒤 train.json items에 type='피드백'으로 더한다.", "items": queue},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"피드백 {len(fb)}건 → 라벨 붙일 구절 {len(queue)}개 → {OUT}")


if __name__ == "__main__":
    main()
