"""학교 생활 API (11.04 하이클래스 반영): 출결 알리기 · 학교소식(공지) · 양식 신청 · 설문 · 오늘(시간표·급식).

이 기능들은 AI를 거치지 않는다. main.py 맨 아래에서 불러온다.
이미 만든 cushion.db에도 쓸 수 있게 표는 시작할 때 없으면 만든다 (schema.sql 은 그대로).
"""
import json
from datetime import date, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.main import ApiError, current, linked, my_class, need, now, row, rows, tx

router = APIRouter()

TABLES = """
CREATE TABLE IF NOT EXISTS attendance (
  id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id), parent_id INTEGER NOT NULL REFERENCES users(id),
  child_name TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('late','absent','early','result')),
  att_date TEXT NOT NULL, detail TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL, checked_at TEXT
);
CREATE TABLE IF NOT EXISTS notices (
  id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id), author_id INTEGER NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL CHECK (kind IN ('circular','class','notice')), title TEXT NOT NULL, body TEXT NOT NULL,
  pinned INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notice_scraps (
  user_id INTEGER NOT NULL REFERENCES users(id), notice_id INTEGER NOT NULL REFERENCES notices(id), PRIMARY KEY (user_id, notice_id)
);
CREATE TABLE IF NOT EXISTS field_trips (
  id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id), parent_id INTEGER NOT NULL REFERENCES users(id),
  child_name TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL, learn_type TEXT NOT NULL,
  place TEXT NOT NULL, stay TEXT, purpose TEXT NOT NULL, created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')), note TEXT, decided_at TEXT
);
CREATE TABLE IF NOT EXISTS surveys (
  id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL REFERENCES classes(id), title TEXT NOT NULL, body TEXT NOT NULL,
  question TEXT NOT NULL, options TEXT NOT NULL, opens_on TEXT NOT NULL, closes_on TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS survey_answers (
  survey_id INTEGER NOT NULL REFERENCES surveys(id), user_id INTEGER NOT NULL REFERENCES users(id),
  option_idx INTEGER NOT NULL, answered_at TEXT NOT NULL, PRIMARY KEY (survey_id, user_id)
);
"""

ATT_KIND = {"late": "지각", "absent": "결석", "early": "조퇴", "result": "결과"}
ATT_DETAIL = ["질병", "미인정", "기타", "출석인정"]
NOTICE_KIND = {"circular": "가정통신문", "class": "학급공지", "notice": "공지사항"}
LEARN_TYPES = ["가족여행", "친지방문", "견학·체험", "기타"]

# 시간표 · 급식: 학교 공개 자료를 읽어 오기 전까지는 예시 값이다 (ponytail: 나이스 연동 때 이 두 개만 바꾸기)
TIMETABLE = [["영어", "도덕", "미술", "수학", "과학"], ["도덕", "한문", "문매", "음악", "국어"],
             ["주제", "한문", "동사", "문학", "수1"], ["일1", "경제", "통사", "수학", "통과"],
             ["수기", "문매", "정보", "수학A", "통과"], ["영어", "진로", "정보", "수학A", "통과"]]
PERIOD_START = ["09:00", "09:55", "10:50", "11:45", "13:20", "14:15"]  # 한 교시 45분, 점심은 12:40
MEALS = [["쌀밥", "미역국", "제육볶음", "배추김치", "요구르트", "깍두기"],
         ["잡곡밥", "순두부찌개", "계란말이", "김치", "바나나", "멸치볶음"],
         ["차수수밥", "편육양파무침", "모듬햄부대찌개", "워터젤리", "아삭이고추무침", "보쌈김치"],
         ["현미밥", "닭곰탕", "불고기", "깍두기", "사과", "시금치나물"],
         ["카레라이스", "콩나물국", "치킨너겟", "단무지", "우유", "샐러드"]]


def setup():
    with tx() as c:
        c.executescript(TABLES)
        have = {r[1] for r in c.execute("PRAGMA table_info(field_trips)")}  # 11.04 처음 만든 DB에는 승인 칸이 없다
        for col, ddl in (("status", "TEXT NOT NULL DEFAULT 'pending'"), ("note", "TEXT"), ("decided_at", "TEXT")):
            if col not in have:
                c.execute(f"ALTER TABLE field_trips ADD COLUMN {col} {ddl}")
        cls = c.execute("SELECT id, teacher_id FROM classes WHERE class_no = 2 ORDER BY id LIMIT 1").fetchone()
        if not cls or c.execute("SELECT 1 FROM notices").fetchone():
            return
        t, today = now(), date.today()
        for kind, title, body, pin in [
            ("class", "진로 연계 체험 안내", "내일은 진로 연계 체험으로 서울 시내 주요 대학을 방문해요.\n1. 늦지 않게 준비할 수 있도록 협조 부탁드려요.\n2. 반드시 교복(또는 체육복)을 입고 와 주세요.", 1),
            ("circular", "3~4월 서울 학부모 마음 상담 프로그램", "서울학부모지원센터에서 건강한 부모-자녀 관계 형성을 지원하기 위해 상담 프로그램을 운영해요.", 0),
            ("notice", "2026 학생회 정부회장 선거 공고 및 등록 안내", "후보 등록은 이번 주 금요일까지예요.", 0),
        ]:
            c.execute("INSERT INTO notices (class_id, author_id, kind, title, body, pinned, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (cls["id"], cls["teacher_id"], kind, title, body, pin, t))
        c.execute("INSERT INTO surveys (class_id, title, body, question, options, opens_on, closes_on, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (cls["id"], "신입생 체육복 만족도 조사", "본교 체육복에 대한 의견을 모아 앞으로 개선하려고 해요. 솔직하게 답해 주세요.",
                   "체육복 가격 대비 체육복의 질에 만족한다.",
                   json.dumps(["매우만족 (10점)", "만족 (8점)", "보통 (6점)", "불만 (4점)", "매우불만 (2점)"], ensure_ascii=False),
                   today.isoformat(), (today + timedelta(days=7)).isoformat(), t))


setup()


def teacher_classes(u):
    need(u, "teacher")
    return [r["id"] for r in rows("SELECT id FROM classes WHERE teacher_id = ? ORDER BY grade, class_no", u["id"])]


def class_access(u, class_id):
    """담임 본인 · 이 반에 연결된 학부모 · 이 반 학생(읽기)"""
    if u["role"] == "teacher":
        my_class(u, class_id)
    elif u["role"] == "student":  # 읽기만: 쓰기 API는 각자 need(...)로 막혀 있다
        if not row("SELECT id FROM class_members WHERE user_id = ? AND class_id = ? AND member_role = 'student'", u["id"], class_id):
            raise ApiError("FORBIDDEN", 403)
    else:
        need(u, "parent")
        linked(u, class_id)


# ───────── 출결 알리기 ─────────
class NewAttendance(BaseModel):
    class_id: int
    kind: Literal["late", "absent", "early", "result"]
    att_date: date
    detail: Literal["질병", "미인정", "기타", "출석인정"]
    reason: str = Field("", max_length=100)


@router.post("/api/parent/attendance", status_code=201)
def send_attendance(b: NewAttendance, u=Depends(current)):
    need(u, "parent")
    m = linked(u, b.class_id)
    with tx() as c:
        aid = c.execute("INSERT INTO attendance (class_id, parent_id, child_name, kind, att_date, detail, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (b.class_id, u["id"], m["child_name"], b.kind, b.att_date.isoformat(), b.detail, b.reason.strip(), now())).lastrowid
    return {"id": aid}


@router.get("/api/parent/classes/{class_id}/attendance")
def my_attendance(class_id: int, u=Depends(current)):
    need(u, "parent")
    linked(u, class_id)
    return {"items": rows("SELECT id, kind, att_date, detail, reason, checked_at FROM attendance WHERE class_id = ? AND parent_id = ? ORDER BY id DESC LIMIT 20",
                          class_id, u["id"])}


@router.get("/api/teacher/attendance")
def teacher_attendance(day: Optional[date] = None, u=Depends(current)):
    ids = teacher_classes(u)
    d = (day or date.today()).isoformat()
    marks = ",".join("?" * len(ids)) or "NULL"
    items = rows(f"SELECT id, class_id, child_name, kind, att_date, detail, reason, created_at, checked_at FROM attendance WHERE att_date = ? AND class_id IN ({marks}) ORDER BY id",
                 d, *ids)
    return {"day": d, "items": items, "pending": sum(i["checked_at"] is None for i in items),
            "counts": {k: sum(i["kind"] == k for i in items) for k in ATT_KIND}}


@router.post("/api/teacher/attendance/{aid}/check")
def check_attendance(aid: int, u=Depends(current)):
    a = row("SELECT class_id FROM attendance WHERE id = ?", aid)
    if not a:
        raise ApiError("NOT_FOUND", 404, "attendance")
    my_class(u, a["class_id"])
    with tx() as c:
        c.execute("UPDATE attendance SET checked_at = COALESCE(checked_at, ?) WHERE id = ?", (now(), aid))
    return {"id": aid}


@router.post("/api/teacher/attendance/check-all")
def check_all_attendance(day: Optional[date] = None, u=Depends(current)):
    ids = teacher_classes(u)
    marks = ",".join("?" * len(ids)) or "NULL"
    with tx() as c:
        cur = c.execute(f"UPDATE attendance SET checked_at = ? WHERE checked_at IS NULL AND att_date = ? AND class_id IN ({marks})",
                        (now(), (day or date.today()).isoformat(), *ids))
    return {"updated": cur.rowcount}


# ───────── 학교소식 (공지) ─────────
class NewNotice(BaseModel):
    class_id: Optional[int] = None
    kind: Literal["circular", "class", "notice"]
    title: str = Field(min_length=1, max_length=60)
    body: str = Field(min_length=1, max_length=2000)
    pinned: bool = False


@router.get("/api/classes/{class_id}/notices")
def notices(class_id: int, kind: Optional[Literal["circular", "class", "notice"]] = None, u=Depends(current)):
    class_access(u, class_id)
    sql = """SELECT n.id, n.kind, n.title, n.body, n.pinned, n.created_at, n.image, t.name author_name,
             (SELECT s.name FROM classes c JOIN schools s ON s.id = c.school_id WHERE c.id = n.class_id) school_name,
             EXISTS(SELECT 1 FROM notice_scraps s WHERE s.notice_id = n.id AND s.user_id = ?) scrapped
             FROM notices n JOIN users t ON t.id = n.author_id WHERE n.class_id = ?"""
    args = [u["id"], class_id]
    if kind:
        sql += " AND n.kind = ?"
        args.append(kind)
    items = rows(sql + " ORDER BY n.pinned DESC, n.id DESC", *args)
    return {"items": [{**i, "pinned": bool(i["pinned"]), "scrapped": bool(i["scrapped"])} for i in items]}


@router.post("/api/teacher/notices", status_code=201)
def new_notice(b: NewNotice, u=Depends(current)):
    ids = teacher_classes(u)
    cid = b.class_id or (ids[0] if ids else None)
    if cid not in ids:
        raise ApiError("FORBIDDEN", 403)
    with tx() as c:
        nid = c.execute("INSERT INTO notices (class_id, author_id, kind, title, body, pinned, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (cid, u["id"], b.kind, b.title.strip(), b.body.strip(), int(b.pinned), now())).lastrowid
    return {"id": nid}


@router.post("/api/notices/{nid}/scrap")
def scrap(nid: int, u=Depends(current)):
    n = row("SELECT class_id FROM notices WHERE id = ?", nid)
    if not n:
        raise ApiError("NOT_FOUND", 404, "notice")
    class_access(u, n["class_id"])
    with tx() as c:
        if c.execute("DELETE FROM notice_scraps WHERE user_id = ? AND notice_id = ?", (u["id"], nid)).rowcount:
            return {"scrapped": False}
        c.execute("INSERT INTO notice_scraps (user_id, notice_id) VALUES (?, ?)", (u["id"], nid))
    return {"scrapped": True}


# ───────── 체험학습 신청서 ─────────
class NewFieldTrip(BaseModel):
    class_id: int
    start_date: date
    end_date: date
    learn_type: Literal["가족여행", "친지방문", "견학·체험", "기타"]
    place: str = Field(min_length=1, max_length=30)
    stay: str = Field("", max_length=30)
    purpose: str = Field(min_length=1, max_length=30)


@router.post("/api/parent/field-trips", status_code=201)
def send_field_trip(b: NewFieldTrip, u=Depends(current)):
    need(u, "parent")
    m = linked(u, b.class_id)
    if b.end_date < b.start_date:
        raise ApiError("VALIDATION", 422, "end before start")
    with tx() as c:
        fid = c.execute("INSERT INTO field_trips (class_id, parent_id, child_name, start_date, end_date, learn_type, place, stay, purpose, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (b.class_id, u["id"], m["child_name"], b.start_date.isoformat(), b.end_date.isoformat(), b.learn_type,
                         b.place.strip(), b.stay.strip(), b.purpose.strip(), now())).lastrowid
    return {"id": fid}


@router.get("/api/teacher/field-trips")
def teacher_field_trips(u=Depends(current)):
    ids = teacher_classes(u)
    marks = ",".join("?" * len(ids)) or "NULL"
    return {"items": rows(f"SELECT id, child_name, start_date, end_date, learn_type, place, stay, purpose, created_at, status, note FROM field_trips WHERE class_id IN ({marks}) ORDER BY id DESC", *ids)}


class Decision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field("", max_length=200)


@router.post("/api/teacher/field-trips/{fid}/decision")
def decide_field_trip(fid: int, b: Decision, u=Depends(current)):
    f = row("SELECT class_id, status FROM field_trips WHERE id = ?", fid)
    if not f:
        raise ApiError("NOT_FOUND", 404, "field trip")
    my_class(u, f["class_id"])
    if f["status"] != "pending":
        raise ApiError("ALREADY_CLOSED", 409)
    with tx() as c:
        c.execute("UPDATE field_trips SET status = ?, note = ?, decided_at = ? WHERE id = ?", (b.decision, b.note.strip(), now(), fid))
    return {"id": fid, "status": b.decision}


@router.get("/api/parent/classes/{class_id}/field-trips")
def my_field_trips(class_id: int, u=Depends(current)):
    need(u, "parent")
    linked(u, class_id)
    return {"items": rows("SELECT id, start_date, end_date, place, status, note FROM field_trips WHERE class_id = ? AND parent_id = ? ORDER BY id DESC LIMIT 5", class_id, u["id"])}


# ───────── 설문 ─────────
class NewSurvey(BaseModel):
    class_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=60)
    body: str = Field("", max_length=1000)
    question: str = Field(min_length=1, max_length=100)
    options: list[str] = Field(min_length=2, max_length=6)
    days: int = Field(7, ge=1, le=60)


class Answer(BaseModel):
    option_idx: int = Field(ge=0, le=5)


def survey_out(s, uid):
    mine = row("SELECT option_idx FROM survey_answers WHERE survey_id = ? AND user_id = ?", s["id"], uid)
    left = (date.fromisoformat(s["closes_on"]) - date.today()).days
    return {**{k: s[k] for k in ("id", "title", "body", "question", "opens_on", "closes_on")}, "options": json.loads(s["options"]),
            "my_answer": mine["option_idx"] if mine else None, "days_left": left, "open": left >= 0}


@router.get("/api/classes/{class_id}/surveys")
def surveys(class_id: int, u=Depends(current)):
    class_access(u, class_id)
    return {"items": [survey_out(s, u["id"]) for s in rows("SELECT * FROM surveys WHERE class_id = ? ORDER BY id DESC", class_id)]}


@router.post("/api/surveys/{sid}/answer", status_code=201)
def answer(sid: int, b: Answer, u=Depends(current)):
    need(u, "parent")
    s = row("SELECT * FROM surveys WHERE id = ?", sid)
    if not s:
        raise ApiError("NOT_FOUND", 404, "survey")
    linked(u, s["class_id"])
    if b.option_idx >= len(json.loads(s["options"])) or date.today().isoformat() > s["closes_on"]:
        raise ApiError("VALIDATION", 422, "closed or bad option")
    with tx() as c:
        c.execute("INSERT OR REPLACE INTO survey_answers (survey_id, user_id, option_idx, answered_at) VALUES (?, ?, ?, ?)", (sid, u["id"], b.option_idx, now()))
    return {"option_idx": b.option_idx}


@router.post("/api/teacher/surveys", status_code=201)
def new_survey(b: NewSurvey, u=Depends(current)):
    ids = teacher_classes(u)
    cid = b.class_id or (ids[0] if ids else None)
    if cid not in ids:
        raise ApiError("FORBIDDEN", 403)
    today = date.today()
    with tx() as c:
        sid = c.execute("INSERT INTO surveys (class_id, title, body, question, options, opens_on, closes_on, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (cid, b.title.strip(), b.body.strip(), b.question.strip(), json.dumps(b.options, ensure_ascii=False),
                         today.isoformat(), (today + timedelta(days=b.days)).isoformat(), now())).lastrowid
    return {"id": sid}


@router.get("/api/teacher/surveys/{sid}/results")
def survey_results(sid: int, u=Depends(current)):
    s = row("SELECT * FROM surveys WHERE id = ?", sid)
    if not s:
        raise ApiError("NOT_FOUND", 404, "survey")
    my_class(u, s["class_id"])
    opts = json.loads(s["options"])
    counts = [0] * len(opts)
    for r in rows("SELECT option_idx FROM survey_answers WHERE survey_id = ?", sid):
        counts[r["option_idx"]] += 1
    return {"question": s["question"], "options": opts, "counts": counts, "total": sum(counts)}


# ───────── 시간표 · 급식: 이번 주 월~금 ─────────
@router.get("/api/classes/{class_id}/timetable")
def timetable(class_id: int, u=Depends(current)):
    class_access(u, class_id)
    d = date.today()
    mon = d - timedelta(days=d.weekday())
    days = [{"date": (mon + timedelta(days=i)).isoformat(), "weekday": "월화수목금"[i], "lunch": "12:40", "meal": MEALS[i],
             "periods": [{"no": n + 1, "subject": TIMETABLE[n][i], "start": PERIOD_START[n]} for n in range(len(TIMETABLE))]} for i in range(5)]
    return {"today": d.isoformat(), "days": days}


# ───────── 홈: 오늘 ─────────
@router.get("/api/classes/{class_id}/today")
def today(class_id: int, u=Depends(current)):
    class_access(u, class_id)
    d = date.today()
    col = min(d.weekday(), 4)
    open_surveys = [s for s in rows("SELECT id, closes_on FROM surveys WHERE class_id = ?", class_id)
                    if s["closes_on"] >= d.isoformat() and not row("SELECT 1 x FROM survey_answers WHERE survey_id = ? AND user_id = ?", s["id"], u["id"])]
    nearest = min((s["closes_on"] for s in open_surveys), default=None)
    return {"date": d.isoformat(), "timetable": [r[col] for r in TIMETABLE], "meal": MEALS[col], "sample": True,
            "open_surveys": len(open_surveys), "survey_days_left": (date.fromisoformat(nearest) - d).days if nearest else None,
            "new_notices": row("SELECT COUNT(*) n FROM notices WHERE class_id = ? AND created_at >= ?", class_id, (d - timedelta(days=2)).isoformat())["n"]}
