"""쿠션톡 API — docs/06_API/API명세_쿠션톡_261102.html 03절.

실행 (backend 폴더에서): .venv/Scripts/python -m uvicorn app.api.main:app --reload
처음 실행하면 cushion.db를 만들고 예시 계정 · 반 · 메시지를 넣는다 (비밀번호 pass1234).
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.ai.analyzer import analyze as ai_analyze, precheck as ai_precheck

BACKEND = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("CUSHION_DB", BACKEND / "cushion.db"))
SCHEMA = BACKEND / "app" / "db" / "schema.sql"
SECRET = os.environ.get("CUSHION_SECRET", "dev-secret-change-me").encode()
TOKEN_DAYS = 14
DEMO_PW = "pass1234"
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 0 · O · 1 · I 뺌

app = FastAPI(title="쿠션톡 API")


# ───────── 공통 ─────────
def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def rows(sql, *a):
    with closing(db()) as c:
        return [dict(r) for r in c.execute(sql, a)]


def row(sql, *a):
    r = rows(sql, *a)
    return r[0] if r else None


@contextmanager
def tx():
    with closing(db()) as c, c:
        yield c


class ApiError(Exception):
    def __init__(self, code, status, message=""):
        self.code, self.status, self.message = code, status, message


@app.exception_handler(ApiError)
def _api_error(_: Request, e: ApiError):
    return JSONResponse({"error": {"code": e.code, "message": e.message}}, status_code=e.status)


@app.exception_handler(RequestValidationError)
def _validation(_: Request, e: RequestValidationError):
    first = e.errors()[0] if e.errors() else {}
    msg = f"{'.'.join(str(x) for x in first.get('loc', []))}: {first.get('msg', '')}"
    return JSONResponse({"error": {"code": "VALIDATION", "message": msg}}, status_code=422)


# ───────── 비밀번호 · 토큰 ─────────
def hash_pw(pw):
    salt = secrets.token_hex(8)
    return f"scrypt${salt}${hashlib.scrypt(pw.encode(), salt=salt.encode(), n=2**14, r=8, p=1).hex()}"


def check_pw(pw, stored):
    if not stored:
        return False
    _, salt, h = stored.split("$")
    return hmac.compare_digest(hashlib.scrypt(pw.encode(), salt=salt.encode(), n=2**14, r=8, p=1).hex(), h)


def make_token(uid):
    body = base64.urlsafe_b64encode(json.dumps({"u": uid, "e": int(time.time()) + TOKEN_DAYS * 86400}).encode()).decode().rstrip("=")
    return f"{body}.{hmac.new(SECRET, body.encode(), 'sha256').hexdigest()}"


def read_token(tok):
    body, _, sig = tok.partition(".")
    if not hmac.compare_digest(sig, hmac.new(SECRET, body.encode(), "sha256").hexdigest()):
        return None
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    return data["u"] if data["e"] > time.time() else None


REVOKED = set()  # ponytail: 서버를 다시 켜면 로그아웃 목록이 사라짐. 문제 되면 revoked_tokens 테이블로.


def current(authorization: Optional[str] = Header(None)):
    tok = (authorization or "").removeprefix("Bearer ").strip()
    uid = read_token(tok) if tok and tok not in REVOKED else None
    u = row("SELECT * FROM users WHERE id = ?", uid) if uid else None
    if not u:
        raise ApiError("UNAUTHORIZED", 401, "login required")
    u["token"] = tok
    return u


def need(u, *roles):
    if u["role"] not in roles:
        raise ApiError("FORBIDDEN", 403, f"role {u['role']}")


def user_out(u):
    return {"id": u["id"], "role": u["role"], "name": u["name"], "school_id": u["school_id"]}


def notify(c, user_id, kind, ref_type, ref_id):
    c.execute("INSERT INTO notifications (user_id, kind, ref_type, ref_id, created_at) VALUES (?, ?, ?, ?, ?)",
              (user_id, kind, ref_type, ref_id, now()))


def new_code(c, class_id, issuer):
    t = now()
    c.execute("UPDATE join_codes SET revoked_at = ? WHERE class_id = ? AND revoked_at IS NULL", (t, class_id))
    exp = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    while True:
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(6))
        try:
            c.execute("INSERT INTO join_codes (class_id, code, issued_by, issued_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                      (class_id, code, issuer, t, exp))
            return {"code": code, "issued_at": t, "expires_at": exp, "expired": False}
        except sqlite3.IntegrityError:
            continue  # 한 번 쓴 글자와 겹침 → 다시 뽑기


# ───────── 메시지 저장 · 분석 (플로우 B) ─────────
def save_message(parent_id, class_id, text, msg_type, due_date, used_suggestion):
    cls = row("SELECT * FROM classes WHERE id = ?", class_id)
    t = now()
    with tx() as c:
        mid = c.execute(
            "INSERT INTO messages (parent_id, teacher_id, class_id, original_text, received_at, original_hash, msg_type, due_date, used_suggestion)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (parent_id, cls["teacher_id"], class_id, text, t, hashlib.sha256((text + t).encode()).hexdigest(),
             msg_type, due_date, int(used_suggestion))).lastrowid
        notify(c, cls["teacher_id"], "new_message", "message", mid)
    return mid, t


def run_analysis(mid):
    m = row("SELECT m.*, c.school_id FROM messages m JOIN classes c ON c.id = m.class_id WHERE m.id = ?", mid)
    r, attempts = None, 0
    for attempts in (1, 2):  # ponytail: 키워드 버전은 바로 끝나서 5초 제한을 걸지 않음. LLM을 붙일 때 타임아웃 추가.
        try:
            r = ai_analyze(m["original_text"])
            break
        except Exception:
            r = None
    with tx() as c:
        if not r:
            c.execute("UPDATE messages SET analysis_status = 'failed' WHERE id = ?", (mid,))
            return
        c.execute(
            "INSERT INTO analyses (message_id, ai_category, urgent_type, summary, requests, masked_count, masked_spans, threat_reason, attempts, model, analyzed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, r["category"], r["urgent_type"], r["summary"], json.dumps(r["requests"], ensure_ascii=False),
             len(r["masked_spans"]), json.dumps(r["masked_spans"]), r["threat_reason"], attempts, r["model"], now()))
        c.execute("UPDATE messages SET analysis_status = 'done', category = ? WHERE id = ?", (r["category"], mid))
        if r["category"] == "urgent":
            notify(c, m["teacher_id"], "urgent", "message", mid)
        if r["category"] == "threat":
            case = c.execute("INSERT INTO threat_cases (message_id, school_id, status, opened_at) VALUES (?, ?, 'new', ?)",
                             (mid, m["school_id"], now())).lastrowid
            for (aid,) in c.execute("SELECT id FROM users WHERE role = 'admin' AND school_id = ?", (m["school_id"],)).fetchall():
                notify(c, aid, "threat", "case", case)


# ───────── 처음 실행: 생성문 + 예시 데이터 ─────────
def init_db():
    if DB_PATH.exists():
        return
    with closing(db()) as c:
        c.executescript(SCHEMA.read_text(encoding="utf-8"))
    t, year = now(), datetime.now().year
    with tx() as c:
        c.execute("INSERT INTO schools (id, name, created_at) VALUES (1, '해오름초등학교', ?), (2, '해오름중학교', ?)", (t, t))

        def user(role, name, login):
            return c.execute("INSERT INTO users (role, name, school_id, login_id, password_hash, created_at) VALUES (?, ?, 1, ?, ?, ?)",
                             (role, name, login, hash_pw(DEMO_PW), t)).lastrowid

        kim, lee, jung = user("teacher", "김하늘", "teacher1"), user("teacher", "이도윤", "teacher2"), user("teacher", "정유나", "teacher3")
        user("admin", "교감", "admin1")
        parents = [user("parent", n, f"parent{i}") for i, n in enumerate(["박지영", "최수진", "한미경"], 1)]
        cls = {}
        for no, tid in ((1, lee), (2, kim), (3, jung)):
            cls[no] = c.execute("INSERT INTO classes (school_id, teacher_id, year, grade, class_no, created_at) VALUES (1, ?, ?, 3, ?, ?)",
                                (tid, year, no, t)).lastrowid
            new_code(c, cls[no], tid)
        for pid, child in zip(parents, ["민서", "하윤", "서연"]):
            c.execute("INSERT INTO class_members (class_id, user_id, member_role, child_name, joined_at) VALUES (?, ?, 'parent', ?, ?)",
                      (cls[2], pid, child, t))
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    examples = [  # 와이어프레임 · 앱 정의서 예시 문구
        (parents[2], "선생님, 다음 주 상담 시간을 잡아 주실 수 있을까요?", "counsel", None),
        (parents[0], "선생님, 애들 하나 제대로 못 보세요? 우리 민서가 짝이랑 안 맞아서 매일 울면서 집에 와요. 그러고도 선생님 소리 듣고 싶으세요? 내일까지 자리 바꿔 주세요.", "seating", tomorrow),
        (parents[0], "답장도 없으시네요. 내일 아침에 교실로 직접 찾아갈 테니 각오하고 계세요.", "other", None),
        (parents[1], "선생님, 하윤이가 쉬는 시간마다 같은 반 친구들한테 맞는다고 해요. 오늘 아침에도 팔에 멍이 든 채로 학교에 갔어요. 꼭 확인 부탁드려요.", "other", None),
    ]
    for pid, text, mt, due in examples:
        run_analysis(save_message(pid, cls[2], text, mt, due, False)[0])


init_db()


# ───────── 요청 몸통 ─────────
MsgType = Literal["counsel", "absence", "seating", "study", "life", "other"]


class Login(BaseModel):
    login_id: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class Signup(BaseModel):
    school_id: int
    name: str = Field(min_length=1, max_length=30)
    login_id: str = Field(min_length=3, max_length=30, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=200)


class Link(BaseModel):
    child_name: str = Field(min_length=1, max_length=30)


class Text(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class NewMessage(BaseModel):
    class_id: int
    text: str = Field(min_length=1, max_length=2000)
    msg_type: MsgType
    due_date: Optional[date] = None
    used_suggestion: bool = False


class Via(BaseModel):
    via: Literal["teacher_sheet", "failed_expand"]


class Body(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class Action(BaseModel):
    action_type: Literal["meeting", "report_office", "report_police", "other"]
    memo: Optional[str] = Field(None, max_length=1000)


class Memo(BaseModel):
    memo: Optional[str] = Field(None, max_length=1000)


class Room(BaseModel):
    grade: int = Field(ge=1, le=6)
    class_no: int = Field(ge=1, le=20)


class Join(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=30)


class ReadIds(BaseModel):
    ids: Optional[list[int]] = None


# ───────── G 로그인 · 가입 ─────────
@app.post("/api/auth/login")
def login(b: Login):
    u = row("SELECT * FROM users WHERE login_id = ?", b.login_id)
    if not u or not check_pw(b.password, u["password_hash"]):
        raise ApiError("WRONG_CREDENTIALS", 401)
    return {"token": make_token(u["id"]), "user": user_out(u)}


@app.get("/api/schools")
def schools(q: str = ""):
    if len(q.strip()) < 2:
        raise ApiError("VALIDATION", 422, "q needs 2+ chars")
    return {"schools": rows("SELECT id, name FROM schools WHERE name LIKE ? ORDER BY name LIMIT 20", f"%{q.strip()}%")}


@app.post("/api/auth/signup", status_code=201)
def signup(b: Signup):
    if not row("SELECT id FROM schools WHERE id = ?", b.school_id):
        raise ApiError("NOT_FOUND", 404, "school")
    if row("SELECT id FROM users WHERE login_id = ?", b.login_id):
        raise ApiError("LOGIN_ID_TAKEN", 409)
    with tx() as c:
        uid = c.execute("INSERT INTO users (role, name, school_id, login_id, password_hash, created_at) VALUES ('parent', ?, ?, ?, ?, ?)",
                        (b.name, b.school_id, b.login_id, hash_pw(b.password), now())).lastrowid
    return {"token": make_token(uid), "user": user_out(row("SELECT * FROM users WHERE id = ?", uid))}


@app.get("/api/me")
def me(u=Depends(current)):
    school = row("SELECT name FROM schools WHERE id = ?", u["school_id"])
    return {"user": {**user_out(u), "school_name": school["name"]}}


@app.post("/api/auth/logout", status_code=204)
def logout(u=Depends(current)):
    REVOKED.add(u["token"])
    return Response(status_code=204)


# ───────── A 학부모 ─────────
def linked(u, class_id):
    m = row("SELECT * FROM class_members WHERE user_id = ? AND class_id = ? AND member_role = 'parent'", u["id"], class_id)
    if not m:
        raise ApiError("NOT_LINKED", 403)
    return m


@app.get("/api/parent/teachers")
def teachers(u=Depends(current)):
    need(u, "parent")
    mine = rows("""SELECT c.id class_id, c.grade, c.class_no, t.name teacher_name, m.child_name,
                   (SELECT MAX(received_at) FROM messages WHERE parent_id = m.user_id AND class_id = c.id) last_at
                   FROM class_members m JOIN classes c ON c.id = m.class_id JOIN users t ON t.id = c.teacher_id
                   WHERE m.user_id = ? AND m.member_role = 'parent' ORDER BY c.grade, c.class_no""", u["id"])
    others = rows("""SELECT c.id class_id, c.grade, c.class_no, t.name teacher_name
                     FROM classes c JOIN users t ON t.id = c.teacher_id
                     WHERE c.school_id = ? AND c.id NOT IN (SELECT class_id FROM class_members WHERE user_id = ?)
                     ORDER BY c.grade, c.class_no""", u["school_id"], u["id"])
    return {"mine": mine, "others": others}


@app.post("/api/parent/classes/{class_id}/link", status_code=201)
def link(class_id: int, b: Link, u=Depends(current)):
    need(u, "parent")
    if not row("SELECT id FROM classes WHERE id = ? AND school_id = ?", class_id, u["school_id"]):
        raise ApiError("NOT_FOUND", 404, "class")
    if row("SELECT id FROM class_members WHERE class_id = ? AND user_id = ?", class_id, u["id"]):
        raise ApiError("ALREADY_LINKED", 409)
    with tx() as c:
        c.execute("INSERT INTO class_members (class_id, user_id, member_role, child_name, joined_at) VALUES (?, ?, 'parent', ?, ?)",
                  (class_id, u["id"], b.child_name, now()))
    return {"class_id": class_id, "child_name": b.child_name}


@app.get("/api/parent/classes/{class_id}/conversation")
def conversation(class_id: int, u=Depends(current)):
    need(u, "parent")
    linked(u, class_id)
    msgs = rows("SELECT id, original_text text, msg_type, due_date, used_suggestion, received_at at FROM messages WHERE parent_id = ? AND class_id = ?",
                u["id"], class_id)
    reps = rows("""SELECT r.id, r.body text, r.sent_at at FROM replies r JOIN messages m ON m.id = r.message_id
                   WHERE m.parent_id = ? AND m.class_id = ?""", u["id"], class_id)
    items = [{"kind": "message", **m, "used_suggestion": bool(m["used_suggestion"])} for m in msgs] + [{"kind": "reply", **r} for r in reps]
    teacher = row("SELECT t.name FROM classes c JOIN users t ON t.id = c.teacher_id WHERE c.id = ?", class_id)
    # ponytail: 대화를 한 번에 다 줌. 길어지면 limit · before_id로 끊기 (명세 01절).
    return {"teacher_name": teacher["name"], "items": sorted(items, key=lambda x: x["at"]), "next_before_id": None}


@app.post("/api/parent/precheck")
def precheck(b: Text, u=Depends(current)):
    need(u, "parent")
    return ai_precheck(b.text)  # 결과는 저장하지 않음 (10.16 결정)


@app.post("/api/parent/messages", status_code=201)
def send_message(b: NewMessage, bg: BackgroundTasks, u=Depends(current)):
    need(u, "parent")
    linked(u, b.class_id)
    mid, t = save_message(u["id"], b.class_id, b.text, b.msg_type, b.due_date.isoformat() if b.due_date else None, b.used_suggestion)
    bg.add_task(run_analysis, mid)
    return {"id": mid, "received_at": t, "analysis_status": "pending"}


# ───────── C 교사 ─────────
INBOX_SQL = """SELECT m.id, m.category, m.analysis_status, m.msg_type, m.due_date, m.received_at, m.teacher_state, m.original_text,
               a.summary, a.masked_count, a.urgent_type, cm.child_name, tc.status case_status
               FROM messages m LEFT JOIN analyses a ON a.message_id = m.id
               LEFT JOIN class_members cm ON cm.user_id = m.parent_id AND cm.class_id = m.class_id
               LEFT JOIN threat_cases tc ON tc.message_id = m.id
               WHERE m.teacher_id = ? ORDER BY m.received_at DESC, m.id DESC"""


def inbox_item(m):
    out = {k: m[k] for k in ("id", "child_name", "category", "analysis_status", "summary", "msg_type", "due_date",
                             "masked_count", "received_at", "teacher_state")}
    if m["category"] == "threat":
        out.update(case_status=m["case_status"], label="공격적 표현")
    return out


@app.get("/api/teacher/inbox")
def inbox(filter: Literal["todo", "notice", "school"] = "todo", u=Depends(current)):
    need(u, "teacher")
    ms = rows(INBOX_SQL, u["id"])
    open_ = [m for m in ms if m["teacher_state"] != "replied"]
    groups = {
        "todo": [m for m in open_ if m["category"] in (None, "normal")],
        "notice": [],  # ponytail: 알림 필터 규칙이 미정(명세 07절)이라 지금은 0개
        "school": [m for m in ms if m["category"] == "threat"],
    }
    day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "counts": {k: len(v) for k, v in groups.items()},
        # ponytail: “마지막 방문 뒤” 대신 최근 24시간. 방문 시각을 저장할 칸이 생기면 바꾸기.
        "masked_since_last_visit": sum(m["masked_count"] or 0 for m in ms if m["received_at"] >= day_ago),
        "urgent": [{"id": m["id"], "child_name": m["child_name"], "urgent_type": m["urgent_type"],
                    "preview": m["original_text"][:40], "received_at": m["received_at"]}
                   for m in open_ if m["category"] == "urgent"],
        "items": [inbox_item(m) for m in groups[filter]],
        "next_before_id": None,
    }


def teacher_message(u, mid):
    m = row("""SELECT m.*, a.summary, a.requests, a.masked_count, a.masked_spans, a.urgent_type, a.threat_reason,
               c.grade, c.class_no, cm.child_name
               FROM messages m LEFT JOIN analyses a ON a.message_id = m.id JOIN classes c ON c.id = m.class_id
               LEFT JOIN class_members cm ON cm.user_id = m.parent_id AND cm.class_id = m.class_id
               WHERE m.id = ?""", mid)
    if not m:
        raise ApiError("NOT_FOUND", 404, "message")
    if m["teacher_id"] != u["id"]:
        raise ApiError("FORBIDDEN", 403)
    return m


def segments(text, spans):
    out, last = [], 0
    for i, s in enumerate(spans, 1):
        out += [{"t": text[last:s["start"]]}, {"mask": i}]
        last = s["end"]
    return out + [{"t": text[last:]}]


def log_view(c, mid, uid, via):
    c.execute("INSERT INTO original_views (message_id, viewer_id, via, viewed_at) VALUES (?, ?, ?, ?)", (mid, uid, via, now()))


@app.get("/api/teacher/messages/{mid}")
def message_detail(mid: int, u=Depends(current)):
    need(u, "teacher")
    m = teacher_message(u, mid)
    done = m["analysis_status"] == "done"
    out = {k: m[k] for k in ("id", "child_name", "grade", "class_no", "received_at", "category", "analysis_status",
                             "msg_type", "due_date", "summary", "masked_count")}
    out["requests"] = json.loads(m["requests"]) if m["requests"] else []
    out["segments"] = segments(m["original_text"], json.loads(m["masked_spans"])) if done and m["category"] != "urgent" else None
    out["original_text"] = None
    with tx() as c:
        if m["teacher_state"] == "new":
            c.execute("UPDATE messages SET teacher_state = 'read', read_at = ? WHERE id = ?", (now(), mid))
        if m["category"] == "urgent":  # 긴급은 원문을 바로 보여 주고 기록
            out["original_text"] = m["original_text"]
            log_view(c, mid, u["id"], "urgent_detail")
    case = row("SELECT status FROM threat_cases WHERE message_id = ?", mid)
    out["case"] = {"status": case["status"], "label": "공격적 표현"} if case else None
    out["replies"] = rows("SELECT id, body, sent_at FROM replies WHERE message_id = ? ORDER BY id", mid)
    return out


@app.post("/api/teacher/messages/{mid}/original")
def message_original(mid: int, b: Via, u=Depends(current)):
    need(u, "teacher")
    m = teacher_message(u, mid)
    with tx() as c:
        log_view(c, mid, u["id"], b.via)
    return {"original_text": m["original_text"], "received_at": m["received_at"],
            "rough_spans": json.loads(m["masked_spans"]) if m["masked_spans"] else []}


@app.post("/api/teacher/messages/{mid}/replies", status_code=201)
def reply(mid: int, b: Body, u=Depends(current)):
    need(u, "teacher")
    m = teacher_message(u, mid)
    t = now()
    with tx() as c:
        rid = c.execute("INSERT INTO replies (message_id, teacher_id, body, sent_at) VALUES (?, ?, ?, ?)", (mid, u["id"], b.body, t)).lastrowid
        c.execute("UPDATE messages SET teacher_state = 'replied', read_at = COALESCE(read_at, ?) WHERE id = ?", (t, mid))
        notify(c, m["parent_id"], "reply", "reply", rid)
    return {"id": rid, "sent_at": t}


# ───────── D 관리자 ─────────
CASE_SQL = """SELECT tc.*, m.original_text, m.received_at, m.original_hash, m.teacher_id, a.threat_reason, a.masked_spans,
              c.grade, c.class_no, t.name teacher_name, cm.child_name
              FROM threat_cases tc JOIN messages m ON m.id = tc.message_id LEFT JOIN analyses a ON a.message_id = m.id
              JOIN classes c ON c.id = m.class_id JOIN users t ON t.id = m.teacher_id
              LEFT JOIN class_members cm ON cm.user_id = m.parent_id AND cm.class_id = m.class_id"""


def admin_case(u, case_id):
    need(u, "admin")
    k = row(CASE_SQL + " WHERE tc.id = ?", case_id)
    if not k:
        raise ApiError("NOT_FOUND", 404, "case")
    if k["school_id"] != u["school_id"]:
        raise ApiError("FORBIDDEN", 403)
    return k


@app.get("/api/admin/cases")
def cases(status: Literal["new", "handled"] = "new", u=Depends(current)):
    need(u, "admin")
    ks = rows(CASE_SQL + " WHERE tc.school_id = ? ORDER BY tc.opened_at DESC", u["school_id"])
    pick = [k for k in ks if (k["status"] == "new") == (status == "new")]
    last = lambda cid: row("SELECT action_type, created_at FROM case_actions WHERE case_id = ? ORDER BY id DESC LIMIT 1", cid)
    return {
        "counts": {"new": sum(k["status"] == "new" for k in ks), "handled": sum(k["status"] != "new" for k in ks)},
        "cases": [{"id": k["id"], "message_id": k["message_id"], "status": k["status"], "label": "공격적 표현",
                   "child_name": k["child_name"], "grade": k["grade"], "class_no": k["class_no"], "teacher_name": k["teacher_name"],
                   "opened_at": k["opened_at"], "last_action": last(k["id"])} for k in pick],
        "next_before_id": None,
    }


@app.get("/api/admin/cases/{case_id}")
def case_detail(case_id: int, u=Depends(current)):
    k = admin_case(u, case_id)
    with tx() as c:
        log_view(c, k["message_id"], u["id"], "admin_evidence")
    recomputed = hashlib.sha256((k["original_text"] + k["received_at"]).encode()).hexdigest()
    return {
        "id": k["id"], "status": k["status"], "original_text": k["original_text"], "received_at": k["received_at"],
        "original_hash": k["original_hash"], "hash_ok": recomputed == k["original_hash"], "threat_reason": k["threat_reason"],
        "rough_spans": json.loads(k["masked_spans"]) if k["masked_spans"] else [],
        "child_name": k["child_name"], "grade": k["grade"], "class_no": k["class_no"], "teacher_name": k["teacher_name"],
        "actions": rows("""SELECT ca.id, ca.action_type, ca.memo, u.name admin_name, ca.created_at FROM case_actions ca
                           JOIN users u ON u.id = ca.admin_id WHERE ca.case_id = ? ORDER BY ca.id""", case_id),
    }


@app.post("/api/admin/cases/{case_id}/actions", status_code=201)
def case_action(case_id: int, b: Action, u=Depends(current)):
    k = admin_case(u, case_id)
    t = now()
    with tx() as c:
        aid = c.execute("INSERT INTO case_actions (case_id, admin_id, action_type, memo, created_at) VALUES (?, ?, ?, ?, ?)",
                        (case_id, u["id"], b.action_type, b.memo, t)).lastrowid
        if k["status"] == "new":
            c.execute("UPDATE threat_cases SET status = 'handled', closed_at = ? WHERE id = ?", (t, case_id))
        notify(c, k["teacher_id"], "case_update", "case", case_id)
    return {"id": aid, "case_status": "handled" if k["status"] == "new" else k["status"], "created_at": t}


@app.post("/api/admin/cases/{case_id}/return")
def case_return(case_id: int, b: Memo, u=Depends(current)):
    k = admin_case(u, case_id)
    if k["status"] == "returned":
        raise ApiError("ALREADY_CLOSED", 409)
    t = now()
    with tx() as c:
        c.execute("UPDATE threat_cases SET status = 'returned', closed_at = ? WHERE id = ?", (t, case_id))
        c.execute("INSERT INTO case_actions (case_id, admin_id, action_type, memo, created_at) VALUES (?, ?, 'return_normal', ?, ?)",
                  (case_id, u["id"], b.memo, t))
        c.execute("UPDATE messages SET category = 'normal' WHERE id = ?", (k["message_id"],))
        notify(c, k["teacher_id"], "case_update", "case", case_id)
    return {"case_status": "returned", "message_category": "normal"}


# ───────── E · F 반 톡방 ─────────
def my_class(u, class_id):
    need(u, "teacher")
    cls = row("SELECT * FROM classes WHERE id = ?", class_id)
    if not cls:
        raise ApiError("NOT_FOUND", 404, "class")
    if cls["teacher_id"] != u["id"]:
        raise ApiError("FORBIDDEN", 403)
    return cls


@app.get("/api/teacher/rooms")
def rooms(u=Depends(current)):
    need(u, "teacher")
    return {"rooms": rows("""SELECT c.id class_id, c.grade, c.class_no,
                             (SELECT COUNT(*) FROM class_members WHERE class_id = c.id AND member_role = 'student') student_count,
                             (SELECT MAX(sent_at) FROM room_messages WHERE class_id = c.id) last_at
                             FROM classes c WHERE c.teacher_id = ? ORDER BY c.grade, c.class_no""", u["id"])}


@app.post("/api/teacher/rooms")
def open_room(b: Room, u=Depends(current)):
    need(u, "teacher")
    year = datetime.now().year
    cls = row("SELECT * FROM classes WHERE school_id = ? AND year = ? AND grade = ? AND class_no = ?", u["school_id"], year, b.grade, b.class_no)
    if cls:
        if cls["teacher_id"] != u["id"]:
            raise ApiError("CLASS_TAKEN", 409)
        return {"class_id": cls["id"], "created": False, "join_code": None}
    with tx() as c:
        cid = c.execute("INSERT INTO classes (school_id, teacher_id, year, grade, class_no, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (u["school_id"], u["id"], year, b.grade, b.class_no, now())).lastrowid
        code = new_code(c, cid, u["id"])
    return JSONResponse({"class_id": cid, "created": True, "join_code": code}, status_code=201)


@app.get("/api/teacher/rooms/{class_id}/join-code")
def join_code(class_id: int, u=Depends(current)):
    my_class(u, class_id)
    jc = row("SELECT code, issued_at, expires_at FROM join_codes WHERE class_id = ? AND revoked_at IS NULL", class_id)
    if not jc:
        raise ApiError("NOT_FOUND", 404, "join code")
    return {**jc, "expired": jc["expires_at"] <= now()}


@app.post("/api/teacher/rooms/{class_id}/join-code", status_code=201)
def renew_code(class_id: int, u=Depends(current)):
    my_class(u, class_id)
    with tx() as c:
        return new_code(c, class_id, u["id"])


@app.post("/api/rooms/join")
def join_room(b: Join):
    code = re.sub(r"\s", "", b.code).upper()
    jc = row("SELECT * FROM join_codes WHERE code = ?", code)
    if not jc:
        raise ApiError("CODE_NOT_FOUND", 404)
    if jc["revoked_at"] or jc["expires_at"] <= now():
        raise ApiError("CODE_EXPIRED", 410)
    name = b.name.strip()
    cls = row("SELECT * FROM classes WHERE id = ?", jc["class_id"])
    same = row("""SELECT u.* FROM users u JOIN class_members m ON m.user_id = u.id
                  WHERE m.class_id = ? AND u.role = 'student' AND u.name = ?""", cls["id"], name)
    if not same:  # 같은 반 같은 이름이면 그 학생으로 이어 줌 (11.02)
        with tx() as c:
            uid = c.execute("INSERT INTO users (role, name, school_id, created_at) VALUES ('student', ?, ?, ?)", (name, cls["school_id"], now())).lastrowid
            c.execute("INSERT INTO class_members (class_id, user_id, member_role, join_code_id, joined_at) VALUES (?, ?, 'student', ?, ?)",
                      (cls["id"], uid, jc["id"], now()))
    u = same or row("SELECT * FROM users WHERE id = ?", uid)
    return {"token": make_token(u["id"]), "user": user_out(u), "class_id": cls["id"], "rejoined": bool(same)}


def room_access(u, class_id):
    cls = row("SELECT * FROM classes WHERE id = ?", class_id)
    if not cls:
        raise ApiError("NOT_FOUND", 404, "class")
    member = row("SELECT id FROM class_members WHERE class_id = ? AND user_id = ? AND member_role = 'student'", class_id, u["id"])
    if cls["teacher_id"] != u["id"] and not member:
        raise ApiError("FORBIDDEN", 403)
    return cls


@app.get("/api/rooms/{class_id}/messages")
def room_messages(class_id: int, after_id: Optional[int] = None, u=Depends(current)):
    cls = room_access(u, class_id)
    sql = """SELECT r.id, r.sender_id, u.name sender_name, u.role sender_role, r.body, r.sent_at
             FROM room_messages r JOIN users u ON u.id = r.sender_id WHERE r.class_id = ?"""
    msgs = (rows(sql + " AND r.id > ? ORDER BY r.id", class_id, after_id) if after_id is not None
            else rows(sql + " ORDER BY r.id DESC LIMIT 50", class_id)[::-1])
    count = row("SELECT COUNT(*) n FROM class_members WHERE class_id = ? AND member_role = 'student'", class_id)["n"]
    return {"class_name": f"{cls['grade']}학년 {cls['class_no']}반", "member_count": count, "messages": msgs}


@app.post("/api/rooms/{class_id}/messages", status_code=201)
def room_send(class_id: int, b: Body, u=Depends(current)):
    room_access(u, class_id)
    t = now()
    with tx() as c:
        rid = c.execute("INSERT INTO room_messages (class_id, sender_id, body, sent_at) VALUES (?, ?, ?, ?)", (class_id, u["id"], b.body, t)).lastrowid
    return {"id": rid, "sent_at": t}


# ───────── 공통: 알림 · 열람 기록 ─────────
@app.get("/api/notifications")
def notifications(unread: bool = False, u=Depends(current)):
    ns = rows("""SELECT n.id, n.kind, n.ref_type, n.ref_id, n.created_at, n.read_at,
                 CASE n.ref_type WHEN 'message' THEN n.ref_id
                   WHEN 'reply' THEN (SELECT message_id FROM replies WHERE id = n.ref_id)
                   WHEN 'case' THEN (SELECT message_id FROM threat_cases WHERE id = n.ref_id) END message_id
                 FROM notifications n WHERE n.user_id = ? ORDER BY n.id DESC LIMIT 50""", u["id"])
    return {"unread_count": sum(n["read_at"] is None for n in ns),
            "notifications": [n for n in ns if not unread or n["read_at"] is None]}


@app.post("/api/notifications/read")
def read_notifications(b: ReadIds, u=Depends(current)):
    with tx() as c:
        if b.ids is None:
            cur = c.execute("UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL", (now(), u["id"]))
        else:
            marks = ",".join("?" * len(b.ids)) or "NULL"
            cur = c.execute(f"UPDATE notifications SET read_at = ? WHERE user_id = ? AND read_at IS NULL AND id IN ({marks})",
                            (now(), u["id"], *b.ids))
    return {"updated": cur.rowcount}


@app.get("/api/messages/{mid}/views")
def views(mid: int, u=Depends(current)):
    m = row("SELECT m.teacher_id, c.school_id FROM messages m JOIN classes c ON c.id = m.class_id WHERE m.id = ?", mid)
    if not m:
        raise ApiError("NOT_FOUND", 404, "message")
    if not ((u["role"] == "admin" and u["school_id"] == m["school_id"]) or u["id"] == m["teacher_id"]):
        raise ApiError("FORBIDDEN", 403)
    return {"views": rows("""SELECT u.name viewer_name, u.role viewer_role, v.via, v.viewed_at FROM original_views v
                             JOIN users u ON u.id = v.viewer_id WHERE v.message_id = ? ORDER BY v.id""", mid)}
