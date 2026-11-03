"""알림장 · 상담 예약 API (11.04).

알림장: 담임이 하루 한 장, 준비물 · 과제 · 전달 세 칸만 쓴다. 학부모는 "확인했어요"를 누르고, 교사는 확인 수만 본다.
상담: 담임이 날짜 · 시간대 · 한 가정당 시간을 열면 시간 칸이 생기고, 학부모가 선착순으로 잡는다 (승인 없이 바로 확정).
      상담 내용은 쿠션이가 거친 표현을 가려서 교사에게 보여 준다 (저장은 원문과 가린 글 둘 다).
main.py 맨 아래에서 불러온다.
"""
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.ai.analyzer import _judge
from app.api.main import ApiError, current, linked, my_class, need, now, room_access, row, rows, tx
from app.api.school import class_access, teacher_classes

router = APIRouter()

TABLES = """
CREATE TABLE IF NOT EXISTS notebooks (
  id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id), author_id INTEGER NOT NULL REFERENCES users(id),
  day TEXT NOT NULL, supplies TEXT NOT NULL DEFAULT '', homework TEXT NOT NULL DEFAULT '', notice TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL, UNIQUE (class_id, day)
);
CREATE TABLE IF NOT EXISTS notebook_reads (
  notebook_id INTEGER NOT NULL REFERENCES notebooks(id), user_id INTEGER NOT NULL REFERENCES users(id),
  read_at TEXT NOT NULL, PRIMARY KEY (notebook_id, user_id)
);
CREATE TABLE IF NOT EXISTS notebook_checks (
  notebook_id INTEGER NOT NULL REFERENCES notebooks(id), user_id INTEGER NOT NULL REFERENCES users(id),
  item TEXT NOT NULL CHECK (item IN ('supplies','homework','notice')), checked_at TEXT NOT NULL, PRIMARY KEY (notebook_id, user_id, item)
);
CREATE TABLE IF NOT EXISTS teacher_alarm (user_id INTEGER PRIMARY KEY REFERENCES users(id), off_until TEXT);
CREATE TABLE IF NOT EXISTS dm_messages (
  id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id), student_id INTEGER NOT NULL REFERENCES users(id),
  sender_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL, body_masked TEXT, masked_count INTEGER NOT NULL DEFAULT 0, sent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS dm_thread ON dm_messages(class_id, student_id, id);
CREATE TABLE IF NOT EXISTS room_reactions (
  message_id INTEGER NOT NULL REFERENCES room_messages(id), user_id INTEGER NOT NULL REFERENCES users(id), PRIMARY KEY (message_id, user_id)
);
CREATE TABLE IF NOT EXISTS room_pins (
  class_id INTEGER PRIMARY KEY REFERENCES classes(id), message_id INTEGER NOT NULL REFERENCES room_messages(id), pinned_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counsel_sessions (
  id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id), title TEXT NOT NULL,
  apply_from TEXT NOT NULL, apply_to TEXT NOT NULL, days TEXT NOT NULL,
  start_time TEXT NOT NULL, end_time TEXT NOT NULL, minutes INTEGER NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counsel_bookings (
  id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES counsel_sessions(id), parent_id INTEGER NOT NULL REFERENCES users(id),
  child_name TEXT NOT NULL, day TEXT NOT NULL, slot TEXT NOT NULL, content TEXT NOT NULL, content_masked TEXT NOT NULL,
  masked_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, canceled_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_counsel_slot ON counsel_bookings(session_id, day, slot) WHERE canceled_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_counsel_parent ON counsel_bookings(session_id, parent_id) WHERE canceled_at IS NULL;
"""


def fmt_day(d):
    return d.isoformat()


def make_slots(start, end, minutes):
    """시작 ~ 끝 사이를 minutes 간격으로 나눈 시작 시각들 (끝 시각을 넘기는 칸은 만들지 않는다)"""
    t0 = datetime.strptime(start, "%H:%M")
    t1 = datetime.strptime(end, "%H:%M")
    out, cur = [], t0
    while cur + timedelta(minutes=minutes) <= t1:
        out.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=minutes)
    return out


def seed():
    with tx() as c:
        c.executescript(TABLES)
        cls = c.execute("SELECT id, teacher_id FROM classes WHERE class_no = 2 ORDER BY id LIMIT 1").fetchone()
        if not cls:
            return
        have = {r[1] for r in c.execute("PRAGMA table_info(room_messages)")}
        for col, ddl in (("reply_to", "INTEGER"), ("body_masked", "TEXT"), ("masked_count", "INTEGER NOT NULL DEFAULT 0")):  # 톡방 답장 · 학생 글 가리기
            if col not in have:
                c.execute(f"ALTER TABLE room_messages ADD COLUMN {col} {ddl}")
        if "request_summary" not in {r[1] for r in c.execute("PRAGMA table_info(analyses)")}:  # 교사에게 보이는 정당한 요청 한 문장
            c.execute("ALTER TABLE analyses ADD COLUMN request_summary TEXT")
        if "done_at" not in {r[1] for r in c.execute("PRAGMA table_info(messages)")}:  # 교사가 확인 체크한 메시지
            c.execute("ALTER TABLE messages ADD COLUMN done_at TEXT")
        if "image" not in {r[1] for r in c.execute("PRAGMA table_info(notices)")}:  # 공지 첨부 이미지 (이미지 올리기 기능이 생기기 전까지는 예시 게시물용)
            c.execute("ALTER TABLE notices ADD COLUMN image TEXT")
        if not c.execute("SELECT 1 FROM notices WHERE image IS NOT NULL").fetchone():
            for title, body, img in [
                ("2학기 학부모 상담주간 신청 안내", "2학기 학부모 상담주간을 운영합니다.\n상담 기간: 11월 9일(월) ~ 11일(수)\n신청은 앱 [상담 예약]에서 선착순으로 받아요.", "/notices/notice-counsel.svg"),
                ("2학기 현장체험학습 안내", "3학년 2반 현장체험학습을 안내드립니다.\n일시: 11월 20일(금) 09:00 ~ 15:00\n장소: 국립중앙박물관\n11월 13일(금)까지 참가 동의서를 제출해 주세요.", "/notices/notice-fieldtrip.svg"),
            ]:
                c.execute("INSERT INTO notices (class_id, author_id, kind, title, body, pinned, created_at, image) VALUES (?, ?, 'circular', ?, ?, 0, ?, ?)",
                          (cls["id"], cls["teacher_id"], title, body, now(), img))
        today = date.today()
        if not c.execute("SELECT 1 FROM notebooks").fetchone():
            for back, (s, h, n) in enumerate([("색연필, 풀, 가위", "수학 익힘책 42쪽", "내일 체육복 입고 오기"), ("리코더", "", "현장학습 동의서 제출")]):
                c.execute("INSERT INTO notebooks (class_id, author_id, day, supplies, homework, notice, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (cls["id"], cls["teacher_id"], fmt_day(today - timedelta(days=back)), s, h, n, now()))
        if not c.execute("SELECT 1 FROM counsel_sessions").fetchone():
            days = [fmt_day(today + timedelta(days=d)) for d in (5, 6, 7)]
            import json
            c.execute("INSERT INTO counsel_sessions (class_id, title, apply_from, apply_to, days, start_time, end_time, minutes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (cls["id"], "2학기 학부모 상담", fmt_day(today), fmt_day(today + timedelta(days=3)), json.dumps(days), "14:00", "18:30", 30, now()))


seed()


# ───────── 반 톡방: 답장 · 하트 · 공지 고정 · 참여자 ─────────
def mask_text(text):
    """학생이 보낸 글: 학부모 메시지와 같은 판단으로 거친 표현을 ▒▒로 가린다. (가린 글, 가린 곳 수)"""
    spans = _judge(text)[0]
    out, last = "", 0
    for sp in sorted(spans, key=lambda x: x["start"]):
        out += text[last:sp["start"]] + "▒▒"
        last = sp["end"]
    return out + text[last:], len(spans)


def enrich_room(msgs, class_id, uid, role="student"):
    """메시지에 하트 수 · 내 하트 · 답장 대상 미리보기를 붙이고, 고정된 공지를 함께 돌려준다 (담임에게는 가린 글의 원문도)"""
    for m in msgs:
        m["body"], orig = m.pop("shown"), m.pop("orig")
        m["original"] = orig if role == "teacher" and m.get("masked_count") else None
    if msgs:
        ids = [m["id"] for m in msgs]
        marks = ",".join("?" * len(ids))
        hearts = {}
        mine = set()
        for r in rows(f"SELECT message_id, user_id FROM room_reactions WHERE message_id IN ({marks})", *ids):
            hearts[r["message_id"]] = hearts.get(r["message_id"], 0) + 1
            if r["user_id"] == uid:
                mine.add(r["message_id"])
        rep_ids = [m["reply_to"] for m in msgs if m.get("reply_to")]
        prev = {}
        if rep_ids:
            rmarks = ",".join("?" * len(rep_ids))
            for r in rows(f"SELECT m.id, COALESCE(m.body_masked, m.body) body, u.name sender_name FROM room_messages m JOIN users u ON u.id = m.sender_id WHERE m.id IN ({rmarks})", *rep_ids):
                prev[r["id"]] = {"id": r["id"], "sender_name": r["sender_name"], "body": r["body"][:60]}
        for m in msgs:
            m["hearts"], m["my_heart"], m["reply"] = hearts.get(m["id"], 0), m["id"] in mine, prev.get(m.get("reply_to"))
    pin = row("""SELECT m.id, COALESCE(m.body_masked, m.body) body, u.name sender_name FROM room_pins p JOIN room_messages m ON m.id = p.message_id
                 JOIN users u ON u.id = m.sender_id WHERE p.class_id = ?""", class_id)
    return msgs, pin


@router.post("/api/rooms/{class_id}/messages/{mid}/heart")
def heart(class_id: int, mid: int, u=Depends(current)):
    room_access(u, class_id)
    if not row("SELECT id FROM room_messages WHERE id = ? AND class_id = ?", mid, class_id):
        raise ApiError("NOT_FOUND", 404, "message")
    with tx() as c:
        if c.execute("DELETE FROM room_reactions WHERE message_id = ? AND user_id = ?", (mid, u["id"])).rowcount:
            return {"my_heart": False}
        c.execute("INSERT INTO room_reactions (message_id, user_id) VALUES (?, ?)", (mid, u["id"]))
    return {"my_heart": True}


class PinReq(BaseModel):
    message_id: Optional[int] = None  # None이면 고정을 푼다


@router.post("/api/rooms/{class_id}/pin")
def pin_message(class_id: int, b: PinReq, u=Depends(current)):
    my_class(u, class_id)  # 담임만
    with tx() as c:
        if b.message_id is None:
            c.execute("DELETE FROM room_pins WHERE class_id = ?", (class_id,))
        else:
            if not c.execute("SELECT 1 FROM room_messages WHERE id = ? AND class_id = ?", (b.message_id, class_id)).fetchone():
                raise ApiError("NOT_FOUND", 404, "message")
            c.execute("INSERT INTO room_pins (class_id, message_id, pinned_at) VALUES (?, ?, ?) ON CONFLICT(class_id) DO UPDATE SET message_id = excluded.message_id, pinned_at = excluded.pinned_at",
                      (class_id, b.message_id, now()))
    return {"message_id": b.message_id}


# ───────── 교사 · 학생 1:1 톡방 (학생이 보낸 글은 AI가 거친 표현을 가림) ─────────
def dm_access(u, class_id, student_id):
    cls = room_access(u, class_id)  # 담임이거나 이 반 학생
    if u["role"] == "student" and u["id"] != student_id:
        raise ApiError("FORBIDDEN", 403)
    if not row("SELECT id FROM class_members WHERE class_id = ? AND user_id = ? AND member_role = 'student'", class_id, student_id):
        raise ApiError("NOT_FOUND", 404, "student")
    return cls


@router.get("/api/rooms/{class_id}/dm")
def dm_threads(class_id: int, u=Depends(current)):
    cls = room_access(u, class_id)
    teacher_name = row("SELECT name FROM users WHERE id = ?", cls["teacher_id"])["name"]
    kids = rows("SELECT u.id, u.name FROM class_members m JOIN users u ON u.id = m.user_id WHERE m.class_id = ? AND m.member_role = 'student' ORDER BY u.name", class_id)
    if u["role"] == "student":
        kids = [k for k in kids if k["id"] == u["id"]]
    out = []
    for k in kids:
        last = row("SELECT COALESCE(body_masked, body) body, sent_at FROM dm_messages WHERE class_id = ? AND student_id = ? ORDER BY id DESC LIMIT 1", class_id, k["id"])
        out.append({"student_id": k["id"], "title": teacher_name if u["role"] == "student" else k["name"], "last": last["body"] if last else None, "last_at": last["sent_at"] if last else None})
    return {"threads": out}


@router.get("/api/rooms/{class_id}/dm/{student_id}/messages")
def dm_messages(class_id: int, student_id: int, u=Depends(current)):
    dm_access(u, class_id, student_id)
    ms = rows("""SELECT d.id, d.sender_id, s.name sender_name, s.role sender_role, COALESCE(d.body_masked, d.body) body, d.body orig, d.masked_count, d.sent_at
                 FROM dm_messages d JOIN users s ON s.id = d.sender_id WHERE d.class_id = ? AND d.student_id = ? ORDER BY d.sent_at, d.id LIMIT 200""", class_id, student_id)
    for m in ms:
        orig = m.pop("orig")
        m["original"] = orig if u["role"] == "teacher" and m["masked_count"] else None
        parts = m["body"].split("▒▒") if m["masked_count"] else None  # 가린 글을 쿠션이 칩 자리로 나눈다
        m["segments"] = [x for i, t in enumerate(parts) for x in ([{"mask": i}] if i else []) + [{"t": t}]] if parts else None
    title = row("SELECT name FROM users WHERE id = ?", student_id)["name"] if u["role"] == "teacher" else row("SELECT t.name FROM classes c JOIN users t ON t.id = c.teacher_id WHERE c.id = ?", class_id)["name"]
    return {"title": title, "messages": ms}


class DmBody(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


@router.post("/api/rooms/{class_id}/dm/{student_id}/messages", status_code=201)
def dm_send(class_id: int, student_id: int, b: DmBody, u=Depends(current)):
    dm_access(u, class_id, student_id)
    masked, n = mask_text(b.body) if u["role"] == "student" else (None, 0)
    with tx() as c:
        did = c.execute("INSERT INTO dm_messages (class_id, student_id, sender_id, body, body_masked, masked_count, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (class_id, student_id, u["id"], b.body.strip(), masked if n else None, n, now())).lastrowid
    return {"id": did, "masked_count": n}


@router.get("/api/rooms/{class_id}/members")
def room_members(class_id: int, u=Depends(current)):
    cls = room_access(u, class_id)
    t = row("SELECT name FROM users WHERE id = ?", cls["teacher_id"])
    kids = rows("SELECT u.name FROM class_members m JOIN users u ON u.id = m.user_id WHERE m.class_id = ? AND m.member_role = 'student' ORDER BY u.name", class_id)
    return {"members": [{"name": t["name"], "role": "teacher"}] + [{"name": k["name"], "role": "student"} for k in kids]}


# ───────── 교사: 확인한 메시지 체크 (체크하면 목록에서 사라진다) ─────────
class DoneReq(BaseModel):
    done: bool = True


@router.post("/api/teacher/messages/{mid}/done")
def mark_done(mid: int, b: DoneReq, u=Depends(current)):
    need(u, "teacher")
    m = row("SELECT teacher_id FROM messages WHERE id = ?", mid)
    if not m:
        raise ApiError("NOT_FOUND", 404, "message")
    if m["teacher_id"] != u["id"]:
        raise ApiError("FORBIDDEN", 403)
    with tx() as c:
        c.execute("UPDATE messages SET done_at = ? WHERE id = ?", (now() if b.done else None, mid))
    return {"id": mid, "done": b.done}


# ───────── 교사 알림 끄기 (긴급 · 안전은 꺼도 온다 — 화면에서 걸러 낼 뿐 메시지는 그대로 쌓인다) ─────────
class AlarmReq(BaseModel):
    until: Optional[datetime] = None  # None이면 켠다


@router.get("/api/teacher/alarm")
def get_alarm(u=Depends(current)):
    need(u, "teacher")
    r = row("SELECT off_until FROM teacher_alarm WHERE user_id = ?", u["id"])
    return {"off_until": r["off_until"] if r else None}


@router.post("/api/teacher/alarm")
def set_alarm(b: AlarmReq, u=Depends(current)):
    need(u, "teacher")
    until = None
    if b.until:
        t = b.until if b.until.tzinfo else b.until.replace(tzinfo=timezone.utc)
        t = t.astimezone(timezone.utc)
        if not (datetime.now(timezone.utc) < t <= datetime.now(timezone.utc) + timedelta(hours=48)):
            raise ApiError("VALIDATION", 422, "until must be within 48h")
        until = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    with tx() as c:
        c.execute("INSERT INTO teacher_alarm (user_id, off_until) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET off_until = excluded.off_until", (u["id"], until))
    return {"off_until": until}


# ───────── 알림장 ─────────
class NewNotebook(BaseModel):
    class_id: Optional[int] = None
    day: Optional[date] = None
    supplies: str = Field("", max_length=100)
    homework: str = Field("", max_length=100)
    notice: str = Field("", max_length=100)


@router.post("/api/teacher/notebooks", status_code=201)
def write_notebook(b: NewNotebook, u=Depends(current)):
    ids = teacher_classes(u)
    cid = b.class_id or (ids[0] if ids else None)
    if cid not in ids:
        raise ApiError("FORBIDDEN", 403)
    if not (b.supplies.strip() or b.homework.strip() or b.notice.strip()):
        raise ApiError("VALIDATION", 422, "empty notebook")
    day = (b.day or date.today()).isoformat()
    with tx() as c:  # 같은 날 다시 쓰면 고친다
        c.execute("""INSERT INTO notebooks (class_id, author_id, day, supplies, homework, notice, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT(class_id, day) DO UPDATE SET supplies = excluded.supplies, homework = excluded.homework, notice = excluded.notice""",
                  (cid, u["id"], day, b.supplies.strip(), b.homework.strip(), b.notice.strip(), now()))
    return {"day": day}


@router.get("/api/classes/{class_id}/notebooks")
def notebooks(class_id: int, u=Depends(current)):
    class_access(u, class_id)
    total = row("SELECT COUNT(*) n FROM class_members WHERE class_id = ? AND member_role = 'parent'", class_id)["n"]
    items = rows("""SELECT n.id, n.day, n.supplies, n.homework, n.notice,
                    (SELECT COUNT(*) FROM notebook_reads r WHERE r.notebook_id = n.id) read_count,
                    EXISTS(SELECT 1 FROM notebook_reads r WHERE r.notebook_id = n.id AND r.user_id = ?) mine
                    FROM notebooks n WHERE n.class_id = ? ORDER BY n.day DESC LIMIT 30""", u["id"], class_id)
    mine = {}
    for r in rows("""SELECT k.notebook_id, k.item FROM notebook_checks k JOIN notebooks n ON n.id = k.notebook_id
                     WHERE k.user_id = ? AND n.class_id = ?""", u["id"], class_id):
        mine.setdefault(r["notebook_id"], []).append(r["item"])
    return {"parent_total": total, "items": [{**i, "mine": bool(i["mine"]), "checks": mine.get(i["id"], [])} for i in items]}


class Check(BaseModel):
    item: Literal["supplies", "homework", "notice"]
    done: bool


@router.post("/api/notebooks/{nid}/check")
def check_item(nid: int, b: Check, u=Depends(current)):
    """알림장 항목 체크 (투두): 학부모 · 학생이 자기 것만 표시한다. 교사에게는 보이지 않는다."""
    n = row("SELECT class_id FROM notebooks WHERE id = ?", nid)
    if not n:
        raise ApiError("NOT_FOUND", 404, "notebook")
    need(u, "parent", "student")
    class_access(u, n["class_id"])
    with tx() as c:
        if b.done:
            c.execute("INSERT OR IGNORE INTO notebook_checks (notebook_id, user_id, item, checked_at) VALUES (?, ?, ?, ?)", (nid, u["id"], b.item, now()))
        else:
            c.execute("DELETE FROM notebook_checks WHERE notebook_id = ? AND user_id = ? AND item = ?", (nid, u["id"], b.item))
    return {"item": b.item, "done": b.done}


@router.post("/api/notebooks/{nid}/read")
def read_notebook(nid: int, u=Depends(current)):
    n = row("SELECT class_id FROM notebooks WHERE id = ?", nid)
    if not n:
        raise ApiError("NOT_FOUND", 404, "notebook")
    need(u, "parent")
    linked(u, n["class_id"])
    with tx() as c:
        c.execute("INSERT OR IGNORE INTO notebook_reads (notebook_id, user_id, read_at) VALUES (?, ?, ?)", (nid, u["id"], now()))
    return {"id": nid}


# ───────── 상담 (선착순 예약) ─────────
class NewCounsel(BaseModel):
    class_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=40)
    apply_from: date
    apply_to: date
    days: list[date] = Field(min_length=1, max_length=10)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    minutes: int = Field(ge=10, le=60)


class Book(BaseModel):
    day: date
    slot: str = Field(pattern=r"^\d{2}:\d{2}$")
    content: str = Field(min_length=1, max_length=200)


def session_out(s, uid, teacher):
    import json
    days = json.loads(s["days"])
    slots = make_slots(s["start_time"], s["end_time"], s["minutes"])
    live = rows("""SELECT b.id, b.parent_id, b.child_name, b.day, b.slot, b.content_masked, b.masked_count FROM counsel_bookings b
                   WHERE b.session_id = ? AND b.canceled_at IS NULL ORDER BY b.day, b.slot""", s["id"])
    taken = {(b["day"], b["slot"]) for b in live}
    mine = next((b for b in live if b["parent_id"] == uid), None)
    left = (date.fromisoformat(s["apply_to"]) - date.today()).days
    out = {"id": s["id"], "title": s["title"], "apply_from": s["apply_from"], "apply_to": s["apply_to"], "minutes": s["minutes"],
           "start_time": s["start_time"], "end_time": s["end_time"], "days_left": left,
           "open": date.fromisoformat(s["apply_from"]) <= date.today() <= date.fromisoformat(s["apply_to"]),
           "days": [{"day": d, "slots": [{"time": t, "taken": (d, t) in taken} for t in slots]} for d in days],
           "booked": len(live), "total": len(days) * len(slots),
           "mine": {k: mine[k] for k in ("id", "day", "slot")} if mine else None}
    if teacher:
        out["bookings"] = [{k: b[k] for k in ("id", "child_name", "day", "slot", "content_masked", "masked_count")} for b in live]
    return out


@router.post("/api/teacher/counsel", status_code=201)
def open_counsel(b: NewCounsel, u=Depends(current)):
    import json
    ids = teacher_classes(u)
    cid = b.class_id or (ids[0] if ids else None)
    if cid not in ids:
        raise ApiError("FORBIDDEN", 403)
    if not make_slots(b.start_time, b.end_time, b.minutes) or b.apply_to < b.apply_from:
        raise ApiError("VALIDATION", 422, "bad time range")
    with tx() as c:
        sid = c.execute("INSERT INTO counsel_sessions (class_id, title, apply_from, apply_to, days, start_time, end_time, minutes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (cid, b.title.strip(), b.apply_from.isoformat(), b.apply_to.isoformat(), json.dumps(sorted(d.isoformat() for d in set(b.days))),
                         b.start_time, b.end_time, b.minutes, now())).lastrowid
    return {"id": sid}


@router.get("/api/classes/{class_id}/counsel")
def counsel(class_id: int, u=Depends(current)):
    class_access(u, class_id)
    return {"items": [session_out(s, u["id"], u["role"] == "teacher") for s in rows("SELECT * FROM counsel_sessions WHERE class_id = ? ORDER BY id DESC", class_id)]}


@router.post("/api/parent/counsel/{sid}/book", status_code=201)
def book(sid: int, b: Book, u=Depends(current)):
    need(u, "parent")
    s = row("SELECT * FROM counsel_sessions WHERE id = ?", sid)
    if not s:
        raise ApiError("NOT_FOUND", 404, "counsel")
    m = linked(u, s["class_id"])
    import json
    if not (s["apply_from"] <= date.today().isoformat() <= s["apply_to"]):
        raise ApiError("ALREADY_CLOSED", 409)
    if b.day.isoformat() not in json.loads(s["days"]) or b.slot not in make_slots(s["start_time"], s["end_time"], s["minutes"]):
        raise ApiError("VALIDATION", 422, "no such slot")
    if row("SELECT id FROM counsel_bookings WHERE session_id = ? AND parent_id = ? AND canceled_at IS NULL", sid, u["id"]):
        raise ApiError("ALREADY_BOOKED", 409)
    spans = _judge(b.content)[0]  # 거친 표현은 가려서 교사에게 (원문은 그대로 보관)
    masked, last = "", 0
    for sp in sorted(spans, key=lambda x: x["start"]):
        masked += b.content[last:sp["start"]] + "▒▒"
        last = sp["end"]
    masked += b.content[last:]
    try:
        with tx() as c:  # 먼저 누른 사람이 가져간다 (같은 칸은 한 명만 들어가도록 DB가 막음)
            bid = c.execute("INSERT INTO counsel_bookings (session_id, parent_id, child_name, day, slot, content, content_masked, masked_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (sid, u["id"], m["child_name"], b.day.isoformat(), b.slot, b.content.strip(), masked.strip(), len(spans), now())).lastrowid
    except sqlite3.IntegrityError:
        raise ApiError("SLOT_TAKEN", 409)
    return {"id": bid, "day": b.day.isoformat(), "slot": b.slot}


@router.post("/api/counsel/bookings/{bid}/cancel")
def cancel_booking(bid: int, u=Depends(current)):
    b = row("SELECT b.*, s.class_id FROM counsel_bookings b JOIN counsel_sessions s ON s.id = b.session_id WHERE b.id = ? AND b.canceled_at IS NULL", bid)
    if not b:
        raise ApiError("NOT_FOUND", 404, "booking")
    if u["role"] == "teacher":
        my_class(u, b["class_id"])
    elif b["parent_id"] != u["id"]:
        raise ApiError("FORBIDDEN", 403)
    with tx() as c:
        c.execute("UPDATE counsel_bookings SET canceled_at = ? WHERE id = ?", (now(), bid))
    return {"id": bid}


# ───────── 교사 톡방: 학부모 · 학생과 주고받은 기록 (카카오톡처럼 최근 순) ─────────
def _masked(text, spans):
    out, last = "", 0
    for sp in sorted(spans, key=lambda x: x["start"]):
        out += text[last:sp["start"]] + "▒▒"
        last = sp["end"]
    return out + text[last:]


@router.get("/api/teacher/talk")
def teacher_talk(class_id: int, u=Depends(current)):
    need(u, "teacher")
    cls = room_access(u, class_id)
    out = []
    for p in rows("""SELECT m.parent_id, cm.child_name FROM messages m
                     LEFT JOIN class_members cm ON cm.user_id = m.parent_id AND cm.class_id = m.class_id
                     WHERE m.teacher_id = ? AND m.class_id = ? GROUP BY m.parent_id""", u["id"], class_id):
        ms = parent_thread(u["id"], class_id, p["parent_id"])
        if ms:
            out.append({"kind": "parent", "key": p["parent_id"], "title": f"{p['child_name']} 보호자", "last": ms[-1]["body"], "last_at": ms[-1]["sent_at"],
                        "unread": sum(1 for m in ms if m.get("new"))})
    for k in rows("SELECT u.id, u.name FROM class_members m JOIN users u ON u.id = m.user_id WHERE m.class_id = ? AND m.member_role = 'student'", class_id):
        last = row("SELECT COALESCE(body_masked, body) body, sent_at FROM dm_messages WHERE class_id = ? AND student_id = ? ORDER BY id DESC LIMIT 1", class_id, k["id"])
        out.append({"kind": "student", "key": k["id"], "title": k["name"], "last": last["body"] if last else None, "last_at": last["sent_at"] if last else None, "unread": 0})
    out.sort(key=lambda t: t["last_at"] or "", reverse=True)
    return {"threads": out}


def segs(text, spans):
    out, last = [], 0
    for i, s in enumerate(sorted(spans, key=lambda x: x["start"]), 1):
        out += [{"t": text[last:s["start"]]}, {"mask": i}]
        last = s["end"]
    return out + [{"t": text[last:]}]


def parent_thread(tid, class_id, parent_id):
    ms = rows("""SELECT m.id, m.original_text, m.received_at, m.category, m.teacher_state, m.done_at, a.masked_spans, a.masked_count, a.request_summary
                 FROM messages m LEFT JOIN analyses a ON a.message_id = m.id
                 WHERE m.teacher_id = ? AND m.class_id = ? AND m.parent_id = ? ORDER BY m.received_at, m.id""", tid, class_id, parent_id)
    out = []
    for m in ms:
        if m["category"] == "threat":  # 공격적 표현은 교사에게 숨긴다: 정당한 요청 한 문장만, 없으면 대화에 올리지 않는다
            if m["request_summary"]:
                out.append({"id": f"m{m['id']}", "mid": m["id"], "from": "parent", "body": m["request_summary"], "sent_at": m["received_at"], "masked_count": 0, "original": None,
                            "urgent": False, "new": m["teacher_state"] == "new", "done": bool(m["done_at"]) or m["teacher_state"] == "replied", "segments": None})
                for r in rows("SELECT id, body, sent_at FROM replies WHERE message_id = ? ORDER BY id", m["id"]):
                    out.append({"id": f"r{r['id']}", "mid": m["id"], "from": "teacher", "body": r["body"], "sent_at": r["sent_at"], "masked_count": 0, "original": None, "urgent": False, "new": False, "done": False, "segments": None})
            continue
        spans = json.loads(m["masked_spans"]) if m["masked_spans"] else []
        urgent = m["category"] == "urgent"
        show = m["original_text"] if urgent or not spans else _masked(m["original_text"], spans)
        out.append({"id": f"m{m['id']}", "mid": m["id"], "from": "parent", "body": show, "sent_at": m["received_at"],
                    "masked_count": 0 if urgent else len(spans), "original": m["original_text"] if spans and not urgent else None,
                    "urgent": urgent, "new": m["teacher_state"] == "new", "done": bool(m["done_at"]) or m["teacher_state"] == "replied",
                    "segments": segs(m["original_text"], spans) if spans and not urgent else None})
        for r in rows("SELECT id, body, sent_at FROM replies WHERE message_id = ? ORDER BY id", m["id"]):
            out.append({"id": f"r{r['id']}", "mid": m["id"], "from": "teacher", "body": r["body"], "sent_at": r["sent_at"], "masked_count": 0, "original": None, "urgent": False, "new": False, "done": False, "segments": None})
    out.sort(key=lambda x: x["sent_at"])
    return out


@router.get("/api/teacher/talk/parent/{parent_id}")
def teacher_talk_parent(parent_id: int, class_id: int, u=Depends(current)):
    need(u, "teacher")
    room_access(u, class_id)
    ms = parent_thread(u["id"], class_id, parent_id)
    if not ms:
        raise ApiError("NOT_FOUND", 404, "thread")
    who = row("SELECT child_name FROM class_members WHERE class_id = ? AND user_id = ?", class_id, parent_id)
    last = [m for m in ms if m["from"] == "parent"][-1]
    return {"title": f"{who['child_name']} 보호자" if who else "보호자", "messages": ms, "reply_to": last["mid"]}
