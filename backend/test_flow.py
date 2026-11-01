"""메시지 한 통 · 위협 · 반 톡방 흐름을 끝까지 돌려 보는 검사. 실행: backend에서 .venv/Scripts/python test_flow.py"""
import os
import tempfile

os.environ["CUSHION_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

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

# C: 메시지함 → 상세(가린 글자 안 옴) → 원문(기록) → 답장
box = c.get("/api/teacher/inbox", headers=teacher).json()
assert box["urgent"] and box["counts"]["school"] == 1
assert any(i["id"] == mid for i in box["items"])
d = c.get(f"/api/teacher/messages/{mid}", headers=teacher).json()
assert d["masked_count"] == 1 and {"mask": 1} in d["segments"] and "제대로 못" not in str(d["segments"])
assert d["original_text"] is None
o = c.post(f"/api/teacher/messages/{mid}/original", json={"via": "teacher_sheet"}, headers=teacher).json()
assert "제대로 못" in o["original_text"]
assert c.post(f"/api/teacher/messages/{mid}/replies", json={"body": "내일 바꿔 볼게요."}, headers=teacher).status_code == 201
conv = c.get(f"/api/parent/classes/{cid}/conversation", headers=parent).json()["items"]
assert conv[-1]["kind"] == "reply"
assert c.get(f"/api/teacher/messages/{mid}", headers=admin).status_code == 403

# 긴급은 답장하면 맨 위에서 내려감
urg = box["urgent"][0]["id"]
c.post(f"/api/teacher/messages/{urg}/replies", json={"body": "바로 확인할게요."}, headers=teacher)
assert not c.get("/api/teacher/inbox", headers=teacher).json()["urgent"]

# D: 위협 사건 → 증거(지문 확인) → 대응 기록 → 담임 알림
case = c.get("/api/admin/cases", headers=admin).json()["cases"][0]
ev = c.get(f"/api/admin/cases/{case['id']}", headers=admin).json()
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

print("flow ok")
