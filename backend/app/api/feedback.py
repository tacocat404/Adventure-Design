"""AI 판단 피드백 (AI 실험 계획 09절 4단계): 담임이 "잘못 가렸어요 · 놓쳤어요"를 남기면 재학습 큐에 쌓인다.

ml/export_feedback.py가 이 표를 읽어 라벨 붙일 문장 목록(ml/data/feedback_queue.json)을 만든다.
이미 만든 cushion.db에도 쓸 수 있게 표는 시작할 때 없으면 만든다 (schema.sql 은 그대로).
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.main import current, need, now, row, teacher_message, tx

router = APIRouter()

TABLE = """
CREATE TABLE IF NOT EXISTS ai_feedback (
  id INTEGER PRIMARY KEY, message_id INTEGER NOT NULL REFERENCES messages(id), teacher_id INTEGER NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL CHECK (kind IN ('over_masked','missed_rough','should_be_threat','should_be_urgent','should_be_normal')),
  ai_category TEXT, model TEXT, note TEXT, created_at TEXT NOT NULL, used_at TEXT,
  UNIQUE (message_id, teacher_id, kind)
);
"""

with tx() as _c:
    _c.executescript(TABLE)


class FeedbackIn(BaseModel):
    kind: Literal["over_masked", "missed_rough", "should_be_threat", "should_be_urgent", "should_be_normal"]
    note: Optional[str] = Field(None, max_length=300)


@router.post("/api/teacher/messages/{mid}/feedback", status_code=201)
def give_feedback(mid: int, b: FeedbackIn, u=Depends(current)):
    need(u, "teacher")
    m = teacher_message(u, mid)  # 내 반 메시지만
    a = row("SELECT ai_category, model FROM analyses WHERE message_id = ?", mid) or {}
    with tx() as c:
        c.execute("""INSERT INTO ai_feedback (message_id, teacher_id, kind, ai_category, model, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT (message_id, teacher_id, kind) DO UPDATE SET note = excluded.note""",
                  (m["id"], u["id"], b.kind, a.get("ai_category"), a.get("model"), b.note, now()))
    return {"ok": True}
