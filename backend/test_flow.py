"""메시지 한 통 · 위협 · 반 톡방 흐름을 끝까지 돌려 보는 검사. 실행: backend에서 .venv/Scripts/python test_flow.py"""
import os
import tempfile

os.environ["CUSHION_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.update(CUSHION_LOCAL_MODEL="off", CNU_API_KEY="", CUSHION_RICH_DEMO="off")  # 흐름만 보는 검사: AI는 키워드 버전으로 (AI는 ml/evaluate.py)

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402

c = TestClient(app)


def login(lid):
    r = c.post("/api/auth/login", json={"login_id": lid, "password": "pass1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


parent, teacher, admin = login("parent1"), login("teacher1"), login("admin1")
assert c.post("/api/auth/login", json={"login_id": "parent1", "password": "x"}).json()["error"]["code"] == "WRONG_CREDENTIALS"
assert c.get("/api/me").status_code == 401

# A: 선생님 목록 → 보내기 전 검사 → 보내기
mine = c.get("/api/parent/teachers", headers=parent).json()["mine"]
assert mine[0]["teacher_name"] == "김하늘" and mine[0]["child_name"] == "민서"
cid = mine[0]["class_id"]
raw = "선생님, 애들 하나 제대로 못 보세요? 내일까지 자리 바꿔 주세요."
pre = c.post("/api/parent/precheck", json={"text": raw}, headers=parent).json()
assert pre["rough"] and pre["suggestions"]
sent = c.post("/api/parent/messages", json={"class_id": cid, "text": raw, "msg_type": "seating", "used_suggestion": False}, headers=parent)
assert sent.status_code == 201, sent.text
mid = sent.json()["id"]
assert c.post("/api/parent/messages", json={"class_id": cid, "text": raw, "msg_type": "nope"}, headers=parent).json()["error"]["code"] == "VALIDATION"

# C: 메시지함 → 상세(쿠션 요약만, 원문 안 옴) → 원문(기록) → 답장
# 거친 표현을 고치지 않고 보낸 일반 메시지는 담임에게 쿠션 요약만 보여 주고, 요약을 눌러야 원문 (11.04 규칙)
box = c.get("/api/teacher/inbox", headers=teacher).json()
assert box["urgent"] and box["counts"]["school"] == 1
assert any(i["id"] == mid for i in box["items"])
d = c.get(f"/api/teacher/messages/{mid}", headers=teacher).json()
assert d["masked_count"] == 1 and d["cushion"] and d["summary"] and d["segments"] is None
assert "제대로 못" not in str(d)
assert d["original_text"] is None
o = c.post(f"/api/teacher/messages/{mid}/original", json={"via": "teacher_sheet"}, headers=teacher).json()
assert "제대로 못" in o["original_text"]
assert c.post(f"/api/teacher/messages/{mid}/replies", json={"body": "내일 바꿔 볼게요."}, headers=teacher).status_code == 201
conv = c.get(f"/api/parent/classes/{cid}/conversation", headers=parent).json()["items"]
assert conv[-1]["kind"] == "reply"
assert c.get(f"/api/teacher/messages/{mid}", headers=admin).status_code == 403

# 공격적 표현: 교사에게는 정당한 요청 한 문장만, 요청이 없으면 아예 안 보이고 건수만 센다. 관리자는 사건으로 받는다
tid = c.post("/api/parent/messages", json={"class_id": cid, "text": "내일 찾아갈 거예요. 채점 기준을 알려 주세요.", "msg_type": "study"}, headers=parent).json()["id"]
bx = c.get("/api/teacher/inbox", headers=teacher).json()
todo_ids = [i["id"] for i in bx["items"]]
assert tid in todo_ids and all(i["category"] == "normal" for i in bx["items"])  # 요청이 섞인 위협은 요청만, 위협 표시 없이
td = c.get(f"/api/teacher/messages/{tid}", headers=teacher).json()
assert td["cushion"] and td["segments"] is None and "찾아" not in (td["summary"] or "") and "채점" in (td["summary"] or "")
# 11.04: 위협 원문도 담임이 쿠션이 요약을 눌러 볼 수 있다 (열람은 기록, 학교에도 넘어가 있음)
assert "찾아" in c.post(f"/api/teacher/messages/{tid}/original", json={"via": "teacher_sheet"}, headers=teacher).json()["original_text"]
sc = c.get("/api/teacher/inbox?filter=school", headers=teacher).json()
assert sc["items"] == [] and sc["counts"]["school"] >= 2  # 건수만
# 학교로 넘어간 메시지가 담임 목록에도 있으면(정당한 요청이 섞인 경우 · 11.04) 담임에게는 쿠션 요약만 보여야 한다
for x in c.get("/api/admin/cases", headers=admin).json()["cases"]:
    if x["message_id"] in todo_ids:
        dd = c.get(f"/api/teacher/messages/{x['message_id']}", headers=teacher).json()
        assert dd["cushion"] and dd["summary"] and dd["segments"] is None, dd
assert len(c.get("/api/admin/cases", headers=admin).json()["cases"]) >= 2

# 긴급은 답장하면 맨 위에서 내려감
urg = box["urgent"][0]["id"]
c.post(f"/api/teacher/messages/{urg}/replies", json={"body": "바로 확인할게요."}, headers=teacher)
assert not c.get("/api/teacher/inbox", headers=teacher).json()["urgent"]

# D: 위협 사건 → 증거(지문 확인) → 대응 기록 → 담임 알림
for case in c.get("/api/admin/cases", headers=admin).json()["cases"]:  # 예시 “각오하고 계세요” 사건을 찾는다
    ev = c.get(f"/api/admin/cases/{case['id']}", headers=admin).json()
    if "각오" in ev["original_text"]:
        break
assert ev["hash_ok"] and "각오" in ev["original_text"]
assert c.post(f"/api/admin/cases/{case['id']}/actions", json={"action_type": "meeting", "memo": "면담"}, headers=admin).json()["case_status"] == "handled"
assert c.get(f"/api/messages/{case['message_id']}/views", headers=admin).json()["views"]
assert any(n["kind"] == "case_update" for n in c.get("/api/notifications", headers=teacher).json()["notifications"])

# E · F: 반 톡방 → 코드 → 학생 참여 → 새 코드면 이전 코드 만료
room = c.post("/api/teacher/rooms", json={"grade": 4, "class_no": 1}, headers=teacher)
assert room.status_code == 201
rid, code = room.json()["class_id"], room.json()["join_code"]["code"]
assert c.post("/api/teacher/rooms", json={"grade": 3, "class_no": 1}, headers=teacher).json()["error"]["code"] == "CLASS_TAKEN"
j = c.post("/api/rooms/join", json={"code": code[:3] + " " + code[3:].lower(), "name": "김서준"}).json()
student = {"Authorization": "Bearer " + j["token"]}
assert c.post("/api/rooms/join", json={"code": code, "name": "김서준"}).json()["rejoined"]
assert c.post("/api/rooms/join", json={"code": "ZZZZZZ", "name": "a"}).json()["error"]["code"] == "CODE_NOT_FOUND"
c.post(f"/api/teacher/rooms/{rid}/join-code", headers=teacher)
assert c.post("/api/rooms/join", json={"code": code, "name": "b"}).json()["error"]["code"] == "CODE_EXPIRED"
c.post(f"/api/rooms/{rid}/messages", json={"body": "선생님 안녕하세요"}, headers=student)
assert c.get(f"/api/rooms/{rid}/messages", headers=teacher).json()["messages"][0]["sender_name"] == "김서준"
assert c.get(f"/api/rooms/{rid}/messages", headers=parent).status_code == 403

# 소셜 로그인 (데모 토큰): 학부모는 바로, 선생님은 관리자 승인 뒤에
sc = c.post("/api/auth/social", json={"provider": "kakao", "token": "demo:새학부모"}).json()
assert sc["needs_signup"]
ok = c.post("/api/auth/social/signup", json={"ticket": sc["ticket"], "role": "parent", "school_id": 1, "name": "새학부모"})
assert ok.status_code == 201 and ok.json()["user"]["role"] == "parent"
assert c.post("/api/auth/social", json={"provider": "kakao", "token": "demo:새학부모"}).json()["user"]["name"] == "새학부모"
tc = c.post("/api/auth/social", json={"provider": "google", "token": "demo:새선생"}).json()
pend = c.post("/api/auth/social/signup", json={"ticket": tc["ticket"], "role": "teacher", "school_id": 1, "name": "새선생"})
assert pend.json() == {"pending": True}
assert c.post("/api/auth/social", json={"provider": "google", "token": "demo:새선생"}).json()["error"]["code"] == "PENDING_APPROVAL"
mem = c.get("/api/admin/members", headers=admin).json()["pending"]
assert [m["name"] for m in mem] == ["새선생"]
assert c.get("/api/admin/members", headers=teacher).status_code == 403
assert c.post(f"/api/admin/members/{mem[0]['id']}/approve", headers=admin).json()["status"] == "active"
assert c.post("/api/auth/social", json={"provider": "google", "token": "demo:새선생"}).json()["user"]["role"] == "teacher"
bad = c.post("/api/auth/social", json={"provider": "kakao", "token": "진짜아닌토큰"})
assert bad.json()["error"]["code"] == "SOCIAL_FAILED"

print("flow ok")

# 학교 생활: 출결 · 공지 · 체험학습 · 설문 · 오늘
cid = c.get("/api/parent/teachers", headers=parent).json()["mine"][0]["class_id"]
att = {"class_id": cid, "kind": "absent", "att_date": __import__("datetime").date.today().isoformat(), "detail": "질병", "reason": "감기로 등교하지 못해요."}
assert c.post("/api/parent/attendance", json=att, headers=parent).status_code == 201
day = c.get("/api/teacher/attendance", headers=teacher).json()
assert day["counts"]["absent"] == 1 and day["pending"] == 1
assert c.post("/api/teacher/attendance/check-all", headers=teacher).json()["updated"] == 1
assert c.get("/api/teacher/attendance", headers=teacher).json()["pending"] == 0
assert c.post("/api/teacher/attendance/check-all", headers=parent).status_code == 403

ns = c.get(f"/api/classes/{cid}/notices", headers=parent).json()["items"]
assert ns[0]["pinned"] and len(ns) == 5 and sum(1 for n in ns if n["image"]) == 2 and ns[0]["school_name"]
assert c.get(f"/api/classes/{cid}/notices?kind=circular", headers=parent).json()["items"][0]["kind"] == "circular"
assert c.post(f"/api/notices/{ns[0]['id']}/scrap", headers=parent).json()["scrapped"] is True
assert c.post("/api/teacher/notices", json={"kind": "notice", "title": "시험 안내", "body": "다음 주 월요일이에요."}, headers=teacher).status_code == 201
assert c.post("/api/teacher/notices", json={"kind": "notice", "title": "x", "body": "y"}, headers=parent).status_code == 403

trip = {"class_id": cid, "start_date": "2026-03-15", "end_date": "2026-03-16", "learn_type": "가족여행", "place": "제주도", "purpose": "박물관 탐방"}
assert c.post("/api/parent/field-trips", json=trip, headers=parent).status_code == 201
assert c.post("/api/parent/field-trips", json={**trip, "end_date": "2026-03-14"}, headers=parent).status_code == 422
ft = c.get("/api/teacher/field-trips", headers=teacher).json()["items"][0]
assert ft["place"] == "제주도" and ft["status"] == "pending"
assert c.post(f"/api/teacher/field-trips/{ft['id']}/decision", json={"decision": "approved", "note": "보고서 내 주세요"}, headers=parent).status_code == 403
assert c.post(f"/api/teacher/field-trips/{ft['id']}/decision", json={"decision": "approved", "note": "보고서 내 주세요"}, headers=teacher).json()["status"] == "approved"
assert c.post(f"/api/teacher/field-trips/{ft['id']}/decision", json={"decision": "rejected"}, headers=teacher).status_code == 409
mine_ft = c.get(f"/api/parent/classes/{cid}/field-trips", headers=parent).json()["items"][0]
assert mine_ft["status"] == "approved" and mine_ft["note"] == "보고서 내 주세요"

sv = c.get(f"/api/classes/{cid}/surveys", headers=parent).json()["items"][0]
assert sv["open"] and sv["my_answer"] is None
assert c.post(f"/api/surveys/{sv['id']}/answer", json={"option_idx": 1}, headers=parent).status_code == 201
assert c.post(f"/api/surveys/{sv['id']}/answer", json={"option_idx": 9}, headers=parent).status_code in (404, 422)
res = c.get(f"/api/teacher/surveys/{sv['id']}/results", headers=teacher).json()
assert res["counts"][1] == 1 and res["total"] == 1
td = c.get(f"/api/classes/{cid}/today", headers=parent).json()
assert td["open_surveys"] == 0 and len(td["timetable"]) == 6
print("학교 생활 흐름 OK")

# 소셜 로그인 (인가 코드 방식): 제공자 호출만 가짜로 바꿔 우리 쪽 흐름을 끝까지 확인
import base64, json as _json, urllib.parse as _up
from app.api import oauth
oauth.CONF.update(KAKAO_CLIENT_ID="kid", KAKAO_CLIENT_SECRET="ks", OAUTH_BASE="http://localhost:5173")
assert "kakao" in c.get("/api/config").json()["ready"] and "naver" not in c.get("/api/config").json()["ready"]
r = c.get("/api/auth/kakao/start?role=parent", follow_redirects=False)
assert r.status_code == 302 and r.headers["location"].startswith("https://kauth.kakao.com/oauth/authorize?") and "client_id=kid" in r.headers["location"]
state = _up.parse_qs(_up.urlparse(r.headers["location"]).query)["state"][0]
oauth.exchange = lambda *a: "demo:코드손님"
def landed(resp):
    frag = resp.headers["location"].split("#login=")[1]
    return _json.loads(base64.urlsafe_b64decode(frag + "=" * (-len(frag) % 4)))
cb = landed(c.get(f"/api/auth/kakao/callback?code=abc&state={state}", follow_redirects=False))
assert cb["kind"] == "signup" and cb["role"] == "parent" and cb["name"] == "코드손님"
su = c.post("/api/auth/social/signup", json={"ticket": cb["ticket"], "role": "parent", "school_id": 1, "name": "코드손님"})
assert su.status_code == 201
again = landed(c.get(f"/api/auth/kakao/callback?code=abc&state={state}", follow_redirects=False))
assert again["kind"] == "in" and again["token"]
assert landed(c.get("/api/auth/kakao/callback?code=abc&state=bad", follow_redirects=False))["kind"] == "error"
assert landed(c.get("/api/auth/naver/start", follow_redirects=False))["kind"] == "error"
print("소셜 로그인 흐름 OK")

# 일반 가입 (아이디 · 비밀번호)
body = {"login_id": "newparent1", "password": "pass12345", "role": "parent", "school_id": 1, "name": "일반학부모"}
r = c.post("/api/auth/signup", json=body)
assert r.status_code == 201 and r.json()["token"] and r.json()["user"]["name"] == "일반학부모"
assert c.post("/api/auth/signup", json=body).json()["error"]["code"] == "ID_TAKEN"
assert c.post("/api/auth/signup", json={**body, "login_id": "ab"}).status_code == 422
assert c.post("/api/auth/signup", json={**body, "login_id": "x2345", "password": "short"}).status_code == 422
assert c.post("/api/auth/login", json={"login_id": "newparent1", "password": "pass12345"}).status_code == 200
t = c.post("/api/auth/signup", json={**body, "login_id": "newteacher1", "role": "teacher", "name": "일반선생님"})
assert t.status_code == 201 and t.json()["pending"] is True
assert c.post("/api/auth/login", json={"login_id": "newteacher1", "password": "pass12345"}).json()["error"]["code"] == "PENDING_APPROVAL"
print("일반 가입 흐름 OK")

# 알림장 · 상담 예약 (선착순)
nb = c.get(f"/api/classes/{cid}/notebooks", headers=parent).json()
assert nb["items"][0]["supplies"] and nb["items"][0]["mine"] is False and nb["parent_total"] >= 3
assert c.post(f"/api/notebooks/{nb['items'][0]['id']}/read", headers=parent).status_code == 200
assert c.get(f"/api/classes/{cid}/notebooks", headers=parent).json()["items"][0]["mine"] is True
assert c.get(f"/api/classes/{cid}/notebooks", headers=teacher).json()["items"][0]["read_count"] == 1
assert c.post("/api/teacher/notebooks", json={"supplies": "", "homework": "", "notice": ""}, headers=teacher).status_code == 422
assert c.post("/api/teacher/notebooks", json={"supplies": "리코더", "homework": "독서록", "notice": "내일 급식 신청"}, headers=teacher).status_code == 201
assert c.post("/api/teacher/notebooks", json={"supplies": "리코더"}, headers=parent).status_code == 403

cs = c.get(f"/api/classes/{cid}/counsel", headers=parent).json()["items"][0]
assert cs["open"] and cs["mine"] is None and len(cs["days"]) == 3 and cs["days"][0]["slots"][0]["time"] == "14:00" and len(cs["days"][0]["slots"]) == 9
day0, slot0 = cs["days"][0]["day"], "15:00"
r1 = c.post(f"/api/parent/counsel/{cs['id']}/book", json={"day": day0, "slot": slot0, "content": "숙제 양이 걱정돼서 상의드리고 싶어요. 선생님 제대로 하세요?"}, headers=parent)
assert r1.status_code == 201, r1.text
other = login("parent2")  # 같은 반이 아니면 막힘, 같은 반 다른 학부모는 같은 칸 선착순 실패
assert c.post(f"/api/parent/counsel/{cs['id']}/book", json={"day": day0, "slot": slot0, "content": "안녕하세요"}, headers=other).status_code in (403, 409)
assert c.post(f"/api/parent/counsel/{cs['id']}/book", json={"day": day0, "slot": "16:00", "content": "다시"}, headers=parent).json()["error"]["code"] == "ALREADY_BOOKED"
assert c.post(f"/api/parent/counsel/{cs['id']}/book", json={"day": day0, "slot": "03:00", "content": "x"}, headers=parent).status_code == 422
tv = c.get(f"/api/classes/{cid}/counsel", headers=teacher).json()["items"][0]
assert tv["booked"] == 1 and tv["bookings"][0]["slot"] == "15:00" and tv["days"][0]["slots"][2]["taken"] is True
assert c.get(f"/api/classes/{cid}/counsel", headers=parent).json()["items"][0]["mine"]["slot"] == "15:00"
assert c.post("/api/teacher/counsel", json={"title": "추가 상담", "apply_from": "2026-11-01", "apply_to": "2026-11-05", "days": ["2026-11-20"], "start_time": "14:00", "end_time": "14:10", "minutes": 30}, headers=teacher).status_code == 422
assert c.post("/api/teacher/counsel", json={"title": "추가 상담", "apply_from": "2026-11-01", "apply_to": "2026-11-05", "days": ["2026-11-20"], "start_time": "14:00", "end_time": "16:00", "minutes": 30}, headers=teacher).status_code == 201
bid = r1.json()["id"]
assert c.post(f"/api/counsel/bookings/{bid}/cancel", headers=other).status_code == 403
assert c.post(f"/api/counsel/bookings/{bid}/cancel", headers=parent).status_code == 200
assert c.get(f"/api/classes/{cid}/counsel", headers=parent).json()["items"][-1]["booked"] == 0
nb0 = c.get(f"/api/classes/{cid}/notebooks", headers=parent).json()["items"][0]
assert nb0["checks"] == []
assert c.post(f"/api/notebooks/{nb0['id']}/check", json={"item": "supplies", "done": True}, headers=parent).status_code == 200
assert c.get(f"/api/classes/{cid}/notebooks", headers=parent).json()["items"][0]["checks"] == ["supplies"]
assert c.get(f"/api/classes/{cid}/notebooks", headers=other).json()["items"][0]["checks"] == []  # 남의 체크는 안 보임
assert c.post(f"/api/notebooks/{nb0['id']}/check", json={"item": "supplies", "done": False}, headers=parent).status_code == 200
assert c.get(f"/api/classes/{cid}/notebooks", headers=parent).json()["items"][0]["checks"] == []
assert c.post(f"/api/notebooks/{nb0['id']}/check", json={"item": "supplies", "done": True}, headers=teacher).status_code == 403
assert c.post(f"/api/notebooks/{nb0['id']}/check", json={"item": "bad", "done": True}, headers=parent).status_code == 422
import datetime as _dt
assert c.get("/api/teacher/alarm", headers=teacher).json()["off_until"] is None
soon = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
assert c.post("/api/teacher/alarm", json={"until": soon}, headers=teacher).json()["off_until"] == soon
assert c.get("/api/teacher/alarm", headers=teacher).json()["off_until"] == soon
past = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
far = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
assert c.post("/api/teacher/alarm", json={"until": past}, headers=teacher).status_code == 422
assert c.post("/api/teacher/alarm", json={"until": far}, headers=teacher).status_code == 422
assert c.post("/api/teacher/alarm", json={"until": soon}, headers=parent).status_code == 403
assert c.post("/api/teacher/alarm", json={"until": None}, headers=teacher).json()["off_until"] is None
print("알림장 · 상담 예약 흐름 OK")

# 학생: 자기 반 읽기만, 다른 반 · 쓰기는 막힘
stu = login("student1")
me_stu = c.get("/api/me", headers=stu).json()["user"]
assert me_stu["role"] == "student"
rooms_cid = cid  # student1은 3학년 2반(데모 반)
assert c.get(f"/api/classes/{rooms_cid}/notices", headers=stu).status_code == 200
assert c.get(f"/api/classes/{rooms_cid}/notebooks", headers=stu).status_code == 200
assert c.get(f"/api/classes/{rooms_cid}/today", headers=stu).status_code == 200
assert c.post("/api/teacher/notices", json={"kind": "notice", "title": "x", "body": "y"}, headers=stu).status_code == 403
assert c.post("/api/parent/attendance", json={"class_id": rooms_cid, "kind": "absent", "att_date": "2026-11-04", "detail": "질병"}, headers=stu).status_code == 403
other_cls = [r for r in c.get("/api/parent/teachers", headers=parent).json()["others"]][0]["class_id"]
assert c.get(f"/api/classes/{other_cls}/notices", headers=stu).status_code == 403
print("학생 읽기 권한 OK")

# 시간표 · 급식
for who in (parent, stu, teacher):
    tt = c.get(f"/api/classes/{cid}/timetable", headers=who).json()
    assert len(tt["days"]) == 5 and len(tt["days"][0]["periods"]) == 6 and tt["days"][0]["periods"][1]["start"] == "09:55" and len(tt["days"][2]["meal"]) == 6
assert c.get(f"/api/classes/{other_cls}/timetable", headers=stu).status_code == 403
print("시간표 OK")

# 반 톡방: 답장 · 하트 · 공지 고정 · 참여자
rm = c.get(f"/api/rooms/{cid}/messages", headers=teacher).json()
assert "pin" in rm and rm["pin"] is None and all("hearts" in m and "reply" in m for m in rm["messages"])
first = c.post(f"/api/rooms/{cid}/messages", json={"body": "첫 메시지"}, headers=teacher).json()["id"]
sent = c.post(f"/api/rooms/{cid}/messages", json={"body": "답장 테스트", "reply_to": first}, headers=stu)
assert sent.status_code == 201
assert c.post(f"/api/rooms/{cid}/messages", json={"body": "없는 대상", "reply_to": 999999}, headers=stu).status_code == 404
last = c.get(f"/api/rooms/{cid}/messages", headers=stu).json()["messages"][-1]
assert last["reply"]["id"] == first and last["hearts"] == 0
assert c.post(f"/api/rooms/{cid}/messages/{last['id']}/heart", headers=teacher).json()["my_heart"] is True
h = [m for m in c.get(f"/api/rooms/{cid}/messages", headers=stu).json()["messages"] if m["id"] == last["id"]][0]
assert h["hearts"] == 1 and h["my_heart"] is False
assert c.post(f"/api/rooms/{cid}/messages/{last['id']}/heart", headers=teacher).json()["my_heart"] is False
assert c.post(f"/api/rooms/{cid}/pin", json={"message_id": last["id"]}, headers=stu).status_code == 403
assert c.post(f"/api/rooms/{cid}/pin", json={"message_id": last["id"]}, headers=teacher).status_code == 200
assert c.get(f"/api/rooms/{cid}/messages", headers=stu).json()["pin"]["id"] == last["id"]
assert c.post(f"/api/rooms/{cid}/pin", json={"message_id": None}, headers=teacher).status_code == 200
assert c.get(f"/api/rooms/{cid}/messages", headers=stu).json()["pin"] is None
mem = c.get(f"/api/rooms/{cid}/members", headers=stu).json()["members"]
assert mem[0]["role"] == "teacher" and len(mem) >= 4
assert c.get(f"/api/rooms/{other_cls}/members", headers=stu).status_code == 403
print("반 톡방 OK")

# 학생 글 AI 가리기 · 1:1 톡방 · 확인 체크
rough = "애들 하나 제대로 못 보세요? 숙제를 왜 이렇게 많이 내세요."
assert c.post(f"/api/rooms/{cid}/messages", json={"body": rough}, headers=stu).status_code == 201
seen_s = c.get(f"/api/rooms/{cid}/messages", headers=stu).json()["messages"][-1]
seen_t = c.get(f"/api/rooms/{cid}/messages", headers=teacher).json()["messages"][-1]
assert seen_s["body"] == rough and seen_s["masked_count"] == 0 and seen_t["original"] is None  # 반 톡방은 AI 검사 없음

sid = c.get("/api/me", headers=stu).json()["user"]["id"]
th_t = c.get(f"/api/rooms/{cid}/dm", headers=teacher).json()["threads"]
th_s = c.get(f"/api/rooms/{cid}/dm", headers=stu).json()["threads"]
assert len(th_t) >= 3 and len(th_s) == 1 and th_s[0]["student_id"] == sid and th_s[0]["title"] == "김하늘"
assert c.post(f"/api/rooms/{cid}/dm/{sid}/messages", json={"body": rough}, headers=stu).json()["masked_count"] >= 1
assert c.post(f"/api/rooms/{cid}/dm/{sid}/messages", json={"body": "네 선생님 알겠습니다"}, headers=teacher).status_code == 201
dm_s = c.get(f"/api/rooms/{cid}/dm/{sid}/messages", headers=stu).json()["messages"]
dm_t = c.get(f"/api/rooms/{cid}/dm/{sid}/messages", headers=teacher).json()["messages"]
assert "▒▒" in dm_s[0]["body"] and dm_s[0]["original"] is None and dm_t[0]["original"] == rough and len(dm_t) == 2
other_stu = [t["student_id"] for t in th_t if t["student_id"] != sid][0]
assert c.get(f"/api/rooms/{cid}/dm/{other_stu}/messages", headers=stu).status_code == 403
assert c.post(f"/api/rooms/{cid}/dm/{other_stu}/messages", json={"body": "x"}, headers=stu).status_code == 403

inbox0 = c.get("/api/teacher/inbox?filter=todo", headers=teacher).json()
n0 = len(inbox0["items"]) + len(inbox0["urgent"])
target = (inbox0["urgent"] or inbox0["items"])[0]["id"]
assert c.post(f"/api/teacher/messages/{target}/done", json={"done": True}, headers=teacher).status_code == 200
inbox1 = c.get("/api/teacher/inbox?filter=todo", headers=teacher).json()
assert len(inbox1["items"]) + len(inbox1["urgent"]) == n0 - 1
assert c.post(f"/api/teacher/messages/{target}/done", json={"done": True}, headers=parent).status_code == 403
assert c.post(f"/api/teacher/messages/{target}/done", json={"done": False}, headers=teacher).status_code == 200
assert len(c.get("/api/teacher/inbox?filter=todo", headers=teacher).json()["items"]) + len(c.get("/api/teacher/inbox?filter=todo", headers=teacher).json()["urgent"]) == n0
print("학생 가리기 · 1:1 톡방 · 확인 체크 OK")

# ── 교사 톡방: 학부모 · 학생 기록이 한 목록에 최근 순으로
talk = c.get("/api/teacher/talk", params={"class_id": cid}, headers=teacher).json()["threads"]
pt = [t for t in talk if t["kind"] == "parent"]
assert pt and any(t["kind"] == "student" for t in talk) and pt[0]["last"]
pm = c.get(f"/api/teacher/talk/parent/{pt[0]['key']}", params={"class_id": cid}, headers=teacher).json()
assert pm["messages"] and pm["messages"][0]["from"] == "parent" and pm["reply_to"]
assert c.get("/api/teacher/talk", params={"class_id": cid}, headers=parent).status_code == 403
print("교사 톡방 기록 OK")
