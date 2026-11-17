"""더미 데이터 검사: 새 DB에 더미 데이터가 들어가고, 더미 계정 화면에 핵심 기능이 보이는지. 실행: backend에서 .venv/Scripts/python test_demo.py"""
import os
import tempfile

os.environ["CUSHION_DB"] = os.path.join(tempfile.mkdtemp(), "demo.db")
os.environ.update(CUSHION_LOCAL_MODEL="off", CNU_API_KEY="")

from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import app  # noqa: E402

c = TestClient(app)


def login(lid):
    r = c.post("/api/auth/login", json={"login_id": lid, "password": "pass1234"})
    assert r.status_code == 200, (lid, r.text)
    return {"Authorization": "Bearer " + r.json()["token"]}


teacher, admin, p1, p4 = login("teacher1"), login("admin1"), login("parent1"), login("parent4")
for lid in ("parent2", "parent3", "parent5", "parent6", "student1", "student2", "student3", "student4", "student5", "student6"):
    login(lid)

# 교사: 메시지함에 긴급 · 일반 · 거친 표현(가림) · 위협이 모두 있다
todo = c.get("/api/teacher/inbox?filter=todo", headers=teacher).json()
assert len(todo["urgent"]) >= 2 and len(todo["items"]) >= 4 and todo["masked_since_last_visit"] >= 1
# 11.05 시연 장면: 방금 온 새 메시지(쿠션 요약 · 평범한 요청 · 긴급). 가림 여부는 판단기가 정해서, 키워드만 쓰는 이 검사에선 안 본다
assert sum(1 for i in todo["items"] + todo["urgent"] if i.get("teacher_state") == "new") >= 3, todo
school = c.get("/api/teacher/inbox?filter=school", headers=teacher).json()
assert school["counts"]["school"] >= 1 and school["items"] == []  # 학교로 넘어간 새 건: 건수만
att = c.get("/api/teacher/attendance", headers=teacher).json()
assert att["counts"]["late"] >= 1 and att["counts"]["early"] >= 1
trips = c.get("/api/teacher/field-trips", headers=teacher).json()["items"]
assert {t["status"] for t in trips} >= {"pending", "approved", "rejected"}

# 관리자: 새 위협 1건 이상, 처리 완료 1건 이상(대응 기록 있음), 가입 대기 2명
cases = c.get("/api/admin/cases?status=new", headers=admin).json()
assert cases["counts"]["new"] >= 1 and cases["counts"]["handled"] >= 1
done = c.get("/api/admin/cases?status=handled", headers=admin).json()["cases"][0]
assert c.get(f"/api/admin/cases/{done['id']}", headers=admin).json()["actions"]
assert len(c.get("/api/admin/members", headers=admin).json()["pending"]) == 2

# 학부모: 답장이 와 있고(안 읽은 알림 포함), 알림장 · 설문 · 상담 · 신청 내역이 보인다
cid = c.get("/api/parent/teachers", headers=p4).json()["mine"][0]["class_id"]
assert c.get("/api/notifications?unread=1", headers=p4).json()["unread_count"] >= 1
assert len(c.get(f"/api/classes/{cid}/notebooks", headers=p4).json()["items"]) >= 5
nbt = c.get(f"/api/classes/{cid}/notebooks", headers=teacher).json()
assert nbt["parent_total"] == 6 and nbt["items"][0]["read_count"] == 4
sv = c.get(f"/api/classes/{cid}/surveys", headers=p1).json()["items"]
assert any(s["open"] and s["my_answer"] is None for s in sv) and any(not s["open"] for s in sv)
cs = c.get(f"/api/classes/{cid}/counsel", headers=teacher).json()["items"][0]
assert cs["booked"] >= 4 and any(b["masked_count"] > 0 for b in cs["bookings"])
assert c.get(f"/api/classes/{cid}/counsel", headers=p4).json()["items"][0]["mine"]
assert len(c.get(f"/api/classes/{cid}/notices", headers=p1).json()["items"]) >= 7
assert c.get(f"/api/rooms/{cid}/messages", headers=teacher).json()["messages"]
print("더미 데이터 OK", {"urgent": len(todo["urgent"]), "todo": len(todo["items"]), "threats": cases["counts"]})
