"""시연용 더미 데이터 (11.04): 더미 계정들로 로그인했을 때 핵심 기능과 여러 기능이 풍부하게 보이게 채운다.

- 이미 켜 둔 DB에도 한 번만 들어간다 (demo_meta 표의 rich_v1 표시로 중복 방지).
- 끄려면 환경 변수 CUSHION_RICH_DEMO=off (흐름 검사 test_flow.py는 이걸 끄고 돈다).
- 계정: parent1~6 · teacher1 · admin1 · student1~6 (비밀번호 모두 pass1234).
  새로 만드는 계정은 parent4(정수빈 · 서준) · parent5(오민정 · 하은) · parent6(강태희 · 지호), 가입 대기 선생님 2명.
"""
import hashlib
import json
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone

from app.ai.analyzer import _judge
from app.api.main import DEMO_PW, hash_pw, notify, now, row, rows, run_analysis, tx
from app.api.care import make_slots

KEY = "rich_v1"
FMT = "%Y-%m-%dT%H:%M:%SZ"


def ago(hours=0, days=0):
    return (datetime.now(timezone.utc) - timedelta(hours=hours, days=days)).strftime(FMT)


def seed():
    if os.environ.get("CUSHION_RICH_DEMO", "on") == "off":
        return
    with tx() as c:
        c.execute("CREATE TABLE IF NOT EXISTS demo_meta (key TEXT PRIMARY KEY, at TEXT NOT NULL)")
        if c.execute("SELECT 1 FROM demo_meta WHERE key = ?", (KEY,)).fetchone():
            return
    teacher = row("SELECT id FROM users WHERE login_id = 'teacher1'")
    cls = row("SELECT id FROM classes WHERE teacher_id = ? AND class_no = 2", teacher["id"]) if teacher else None
    admin = row("SELECT id FROM users WHERE login_id = 'admin1'")
    if not (teacher and cls and admin):
        return
    cid, tid, aid = cls["id"], teacher["id"], admin["id"]
    today = date.today()

    # ───── 계정: 학부모 3명 더, 가입 대기 선생님 2명
    def user(role, name, login, child=None):
        u = row("SELECT id FROM users WHERE login_id = ?", login)
        if u:
            return u["id"]
        with tx() as c:
            uid = c.execute("INSERT INTO users (role, name, school_id, login_id, password_hash, created_at) VALUES (?, ?, 1, ?, ?, ?)",
                            (role, name, login, hash_pw(DEMO_PW), now())).lastrowid
            if child:
                c.execute("INSERT INTO class_members (class_id, user_id, member_role, child_name, joined_at) VALUES (?, ?, 'parent', ?, ?)", (cid, uid, child, now()))
        return uid

    p = {i: row("SELECT id FROM users WHERE login_id = ?", f"parent{i}") for i in (1, 2, 3)}
    p = {i: (v["id"] if v else None) for i, v in p.items()}
    p[4], p[5], p[6] = user("parent", "정수빈", "parent4", "서준"), user("parent", "오민정", "parent5", "하은"), user("parent", "강태희", "parent6", "지호")
    s = {i: (row("SELECT id FROM users WHERE login_id = ?", f"student{i}") or {}).get("id") for i in (1, 2, 3)}
    with tx() as c:
        for name, login, role in (("이서윤", "pending_teacher", "teacher"), ("최민호", "pending_admin", "admin")):
            if not c.execute("SELECT 1 FROM users WHERE login_id = ?", (login,)).fetchone():
                c.execute("INSERT INTO users (role, name, school_id, login_id, password_hash, provider, provider_uid, status, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, 'pending', ?)",
                          (role, name, login, hash_pw(DEMO_PW), "kakao" if role == "teacher" else None, f"demo:{name}" if role == "teacher" else None, ago(hours=5)))

    # ───── 메시지: 핵심 기능이 골고루 보이게 (정상 · 거친 표현 · 긴급 · 위협 · 답장 · 제안 문장)
    def message(parent, text, mtype, hours_ago, due=None, used=False, reply=None, reply_after=1, unread_reply=False):
        t = ago(hours=hours_ago)
        with tx() as c:
            mid = c.execute("INSERT INTO messages (parent_id, teacher_id, class_id, original_text, received_at, original_hash, msg_type, due_date, used_suggestion) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (parent, tid, cid, text, t, hashlib.sha256((text + t).encode()).hexdigest(), mtype, due, int(used))).lastrowid
        run_analysis(mid)
        with tx() as c:
            if reply:
                rt = ago(hours=max(hours_ago - reply_after, 0.2))
                rid = c.execute("INSERT INTO replies (message_id, teacher_id, body, sent_at) VALUES (?, ?, ?, ?)", (mid, tid, reply, rt)).lastrowid
                c.execute("UPDATE messages SET teacher_state = 'replied', read_at = ? WHERE id = ?", (rt, mid))
                c.execute("INSERT INTO notifications (user_id, kind, ref_type, ref_id, created_at, read_at) VALUES (?, 'reply', 'reply', ?, ?, ?)", (parent, rid, rt, None if unread_reply else rt))
            else:
                notify(c, tid, "new_message", "message", mid)
        return mid

    tomorrow, after = (today + timedelta(days=1)).isoformat(), (today + timedelta(days=2)).isoformat()
    message(p[1], "민서가 방과후 영어 수업을 신청하고 싶어요. 접수 기간이 언제인지 알려 주세요.", "study", 72,
            reply="접수는 이번 주 금요일까지예요. 신청서는 알림장에 안내해 둘게요.")
    message(p[2], "선생님, 하윤이 학습 진도가 걱정돼서 상담을 요청드리고 싶어요. 가능한 시간을 알려 주세요.", "counsel", 48, used=True,
            reply="상담 기간에 앱에서 편한 시간으로 예약해 주세요. 하윤이 이야기 나눠요.")
    message(p[4], "선생님, 서준이가 땅콩 알레르기가 있어서 현장체험학습 때 도시락만 챙겨 보내도 될까요? 확인 부탁드려요.", "life", 30,
            reply="네, 도시락 지참하셔도 됩니다. 간식 알레르기도 확인해 둘게요.", reply_after=2, unread_reply=True)
    message(p[6], "지호가 어제부터 목이 아파서 오늘 조퇴하고 병원에 가야 해요. 알림장 내용은 어떻게 확인하면 될까요?", "absence", 6,
            reply="걱정되시겠어요. 알림장은 앱 홈에서 바로 확인하실 수 있어요. 조퇴는 출결 알리기로 남겨 주세요.", reply_after=2)
    message(p[5], "숙제가 너무 많아요. 애가 밤 11시까지 못 자는데 선생님은 아이들 생각을 하긴 하시나요? 줄여 주세요.", "study", 4, due=tomorrow)
    message(p[4], "자리를 앞쪽으로 옮겨 주실 수 있을까요? 서준이가 칠판이 잘 안 보인대요.", "seating", 2, due=after)
    message(p[6], "지호가 오늘 체육 시간에 다쳤다고 하는데 팔이 많이 부어 있어요. 학교에서 상황 확인해 주세요.", "life", 1)
    message(p[6], "이번에도 답장 안 하시면 내일 학교로 찾아갈 테니 각오하고 계세요. 교육청에도 알리겠습니다.", "other", 3)

    # 지난 위협 건: 관리자가 면담으로 처리한 기록이 남아 있는 "처리 완료" 예시
    old = message(p[5], "아이 일을 이렇게 처리하면 가만두지 않겠습니다. 내일 찾아갈 테니 각오하세요.", "other", 50)
    case = row("SELECT id FROM threat_cases WHERE message_id = ?", old)
    if case:
        with tx() as c:
            c.execute("UPDATE threat_cases SET status = 'handled', opened_at = ?, closed_at = ? WHERE id = ?", (ago(hours=50), ago(hours=44), case["id"]))
            c.execute("INSERT INTO case_actions (case_id, admin_id, action_type, memo, created_at) VALUES (?, ?, 'meeting', ?, ?)",
                      (case["id"], aid, "학부모 면담 진행(교감 · 담임 동석). 오해를 풀고 이후 앱으로 정상 소통하기로 함.", ago(hours=44)))

    # ───── 출결 (오늘 · 어제)
    with tx() as c:
        for par, child, kind, day, detail, reason, hrs, checked in [
            (p[4], "서준", "late", today, "질병", "아침에 병원에 들렀다 가요.", 5, False),
            (p[5], "하은", "early", today, "기타", "14시 치과 예약이 있어요.", 3, False),
            (p[2], "하윤", "absent", today - timedelta(days=1), "질병", "감기로 하루 쉬었어요.", 30, True),
        ]:
            if par and not c.execute("SELECT 1 FROM attendance WHERE parent_id = ? AND att_date = ?", (par, day.isoformat())).fetchone():
                c.execute("INSERT INTO attendance (class_id, parent_id, child_name, kind, att_date, detail, reason, created_at, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (cid, par, child, kind, day.isoformat(), detail, reason, ago(hours=hrs), ago(hours=hrs - 1) if checked else None))

        # ───── 체험학습 신청: 대기 · 승인 · 반려
        for par, child, st, note, place, purpose, d0 in [
            (p[2], "하윤", "approved", "복귀 후 3일 안에 체험 보고서를 내 주세요.", "경주", "신라 유적지 탐방", 14),
            (p[5], "하은", "rejected", "시험 기간과 겹쳐요. 다른 날짜로 다시 신청해 주세요.", "부산", "가족 친지 방문", 6),
            (p[4], "서준", "pending", None, "강릉", "해양 박물관 견학", 20),
        ]:
            if par and not c.execute("SELECT 1 FROM field_trips WHERE parent_id = ?", (par,)).fetchone():
                start = (today + timedelta(days=d0)).isoformat()
                c.execute("INSERT INTO field_trips (class_id, parent_id, child_name, start_date, end_date, learn_type, place, stay, purpose, created_at, status, note, decided_at) VALUES (?, ?, ?, ?, ?, '가족여행', ?, '', ?, ?, ?, ?, ?)",
                          (cid, par, child, start, (today + timedelta(days=d0 + 1)).isoformat(), place, purpose, ago(hours=26), st, note, None if st == "pending" else ago(hours=10)))

        # ───── 공지 · 설문
        for kind, title, body, hrs in [
            ("notice", "독감 예방접종 안내", "11월 12일(수) 오전에 보건실에서 독감 예방접종을 해요. 동의서를 11일까지 제출해 주세요.", 20),
            ("class", "11월 독서 주간 안내", "이번 달 마지막 주는 독서 주간이에요. 읽은 책 한 권을 소개하는 독서록을 준비해 주세요.", 8),
        ]:
            if not c.execute("SELECT 1 FROM notices WHERE title = ?", (title,)).fetchone():
                c.execute("INSERT INTO notices (class_id, author_id, kind, title, body, pinned, created_at) VALUES (?, ?, ?, ?, ?, 0, ?)", (cid, tid, kind, title, body, ago(hours=hrs)))
        sv = c.execute("SELECT id FROM surveys WHERE title LIKE '신입생 체육복%' ORDER BY id LIMIT 1").fetchone()
        if sv:
            for par, idx in ((p[2], 1), (p[3], 0), (p[4], 1), (p[5], 3)):
                c.execute("INSERT OR IGNORE INTO survey_answers (survey_id, user_id, option_idx, answered_at) VALUES (?, ?, ?, ?)", (sv[0], par, idx, ago(hours=9)))
        if not c.execute("SELECT 1 FROM surveys WHERE title = '급식 만족도 조사'").fetchone():
            sid = c.execute("INSERT INTO surveys (class_id, title, body, question, options, opens_on, closes_on, created_at) VALUES (?, '급식 만족도 조사', '이번 학기 급식에 대한 의견을 들려 주세요.', '급식 메뉴에 만족하나요?', ?, ?, ?, ?)",
                            (cid, json.dumps(["매우 만족", "만족", "보통", "불만"], ensure_ascii=False), (today - timedelta(days=14)).isoformat(), (today - timedelta(days=7)).isoformat(), ago(days=14))).lastrowid
            for par, idx in ((p[1], 1), (p[2], 0), (p[3], 1), (p[4], 2), (p[5], 1), (p[6], 1)):
                c.execute("INSERT OR IGNORE INTO survey_answers (survey_id, user_id, option_idx, answered_at) VALUES (?, ?, ?, ?)", (sid, par, idx, ago(days=10)))

        # ───── 알림장: 지난 며칠 + 확인 현황 + 학부모 · 학생 체크
        for back, (sup, hw, nt) in {2: ("실내화, 줄넘기", "독서록 1편", ""), 3: ("", "받아쓰기 연습", "학부모 상담 신청 기간 안내"), 4: ("물감, 팔레트", "", "내일 미술 수업 있어요")}.items():
            c.execute("INSERT OR IGNORE INTO notebooks (class_id, author_id, day, supplies, homework, notice, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (cid, tid, (today - timedelta(days=back)).isoformat(), sup, hw, nt, ago(days=back)))
        for n in c.execute("SELECT id, day FROM notebooks WHERE class_id = ?", (cid,)).fetchall():
            is_today = n[1] == today.isoformat()
            readers = [p[2], p[3], p[4], p[6]] if is_today else [p[i] for i in (1, 2, 3, 4, 5, 6)]  # 오늘은 6명 중 4명만 확인
            for par in readers:
                c.execute("INSERT OR IGNORE INTO notebook_reads (notebook_id, user_id, read_at) VALUES (?, ?, ?)", (n[0], par, ago(hours=2)))
            if is_today:
                for uid, item in ((p[2], "supplies"), (p[2], "homework"), (p[4], "supplies"), (s[1], "supplies"), (s[1], "notice"), (s[2], "supplies")):
                    if uid:
                        c.execute("INSERT OR IGNORE INTO notebook_checks (notebook_id, user_id, item, checked_at) VALUES (?, ?, ?, ?)", (n[0], uid, item, ago(hours=1)))

        # ───── 상담 예약 (선착순): 일부 칸이 이미 찼고, 거친 표현은 가려진 채 교사에게
        ss = c.execute("SELECT id, days, start_time, end_time, minutes FROM counsel_sessions WHERE class_id = ? ORDER BY id LIMIT 1", (cid,)).fetchone()
        if ss:
            days, slots = json.loads(ss[1]), make_slots(ss[2], ss[3], ss[4])
            for par, child, di, si, text in [
                (p[2], "하윤", 0, 1, "학습 진도가 걱정돼서 상의드리고 싶어요."),
                (p[3], "서연", 0, 3, "친구 관계가 어떤지 궁금해요."),
                (p[4], "서준", 1, 0, "수업 시간에 집중을 잘 못한다고 들었어요. 어떻게 도와주면 좋을까요?"),
                (p[5], "하은", 1, 2, "애들 하나 제대로 못 보세요? 숙제를 왜 이렇게 많이 내세요. 줄여 주세요."),
            ]:
                if not par or di >= len(days) or si >= len(slots):
                    continue
                spans = _judge(text)[0]
                masked, last = "", 0
                for sp in sorted(spans, key=lambda x: x["start"]):
                    masked += text[last:sp["start"]] + "▒▒"
                    last = sp["end"]
                masked += text[last:]
                try:
                    c.execute("INSERT INTO counsel_bookings (session_id, parent_id, child_name, day, slot, content, content_masked, masked_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (ss[0], par, child, days[di], slots[si], text, masked, len(spans), ago(hours=7)))
                except sqlite3.IntegrityError:
                    pass

        # ───── 반 톡방: 교사와 학생 대화
        if s[1] and not c.execute("SELECT 1 FROM room_messages WHERE class_id = ?", (cid,)).fetchone():
            for who, body, hrs in [
                (tid, "다들 좋은 아침! 오늘 1교시는 미술이에요. 준비물 챙겼나요?", 8),
                (s[1], "네! 색연필이랑 풀 챙겼어요!", 7.8),
                (s[2], "저는 가위를 깜빡했어요 ㅠㅠ", 7.7),
                (tid, "짝꿍한테 빌리면 돼요. 다음부터는 알림장 꼭 확인해요.", 7.5),
                (s[3], "선생님 내일 체육복 입고 와야 하죠?", 7.2),
                (tid, "맞아요. 알림장 전달 칸에 써 뒀어요 :)", 7.0),
            ]:
                if who:
                    c.execute("INSERT INTO room_messages (class_id, sender_id, body, sent_at) VALUES (?, ?, ?, ?)", (cid, who, body, ago(hours=hrs)))

        c.execute("INSERT INTO demo_meta (key, at) VALUES (?, ?)", (KEY, now()))


def seed_chat():
    """톡방 더미 (v2): 어제 대화(날짜 구분선), 답장, 하트, 고정 공지"""
    if os.environ.get("CUSHION_RICH_DEMO", "on") == "off":
        return
    with tx() as c:
        c.execute("CREATE TABLE IF NOT EXISTS demo_meta (key TEXT PRIMARY KEY, at TEXT NOT NULL)")
        if c.execute("SELECT 1 FROM demo_meta WHERE key = 'rich_chat_v1'").fetchone():
            return
    teacher = row("SELECT id FROM users WHERE login_id = 'teacher1'")
    cls = row("SELECT id FROM classes WHERE teacher_id = ? AND class_no = 2", teacher["id"]) if teacher else None
    s = {i: (row("SELECT id FROM users WHERE login_id = ?", f"student{i}") or {}).get("id") for i in (1, 2, 3)}
    if not (cls and all(s.values())):
        return
    cid, tid = cls["id"], teacher["id"]
    with tx() as c:
        def add(who, body, hrs, reply=None):
            return c.execute("INSERT INTO room_messages (class_id, sender_id, body, sent_at, reply_to) VALUES (?, ?, ?, ?, ?)", (cid, who, body, ago(hours=hrs), reply)).lastrowid
        add(tid, "내일 아침 조회는 8시 40분이에요. 늦지 않게 와요.", 28)
        add(tid, "숙제는 알림장에 써 둔 것만 하면 돼요.", 27.9)
        add(s[1], "네 알겠습니다!", 27.5)
        add(s[3], "독서록도 내일까지예요?", 27.2)
        add(tid, "독서록은 금요일까지예요.", 27.0, None)
        msgs = c.execute("SELECT id, sender_id, body FROM room_messages WHERE class_id = ? ORDER BY id", (cid,)).fetchall()
        by = {m[2]: m[0] for m in msgs}
        # 오늘 대화에 답장 · 하트 · 새 메시지
        add(s[1], "내 가위 빌려줄게!", 7.6, by.get("저는 가위를 깜빡했어요 ㅠㅠ"))
        pin = add(tid, "내일은 체육복 입고 와요. 알림장 전달 칸에도 써 뒀어요.", 6.5)
        add(s[2], "네 선생님!", 6.4)
        add(s[3], "체육복 안 가져왔으면요?", 6.3)
        add(tid, "그럼 내일 아침에 말해 줘요.", 6.2, None)
        for mid, who in ((pin, s[1]), (pin, s[2]), (pin, s[3]), (by.get("선생님 내일 체육복 입고 와야 하죠?"), tid), (by.get("네 알겠습니다!"), tid), (by.get("저는 가위를 깜빡했어요 ㅠㅠ"), s[1])):
            if mid:
                c.execute("INSERT OR IGNORE INTO room_reactions (message_id, user_id) VALUES (?, ?)", (mid, who))
        c.execute("INSERT OR REPLACE INTO room_pins (class_id, message_id, pinned_at) VALUES (?, ?, ?)", (cid, pin, ago(hours=6)))
        c.execute("INSERT INTO demo_meta (key, at) VALUES ('rich_chat_v1', ?)", (now(),))


def seed_dm():
    """교사 · 학생 1:1 톡방 더미 (rich_dm_v1): 학생 글은 실제 가리기를 거쳐 저장한다"""
    if os.environ.get("CUSHION_RICH_DEMO", "on") == "off":
        return
    from app.api.care import mask_text
    with tx() as c:
        c.execute("CREATE TABLE IF NOT EXISTS demo_meta (key TEXT PRIMARY KEY, at TEXT NOT NULL)")
        if c.execute("SELECT 1 FROM demo_meta WHERE key = 'rich_dm_v1'").fetchone():
            return
    teacher = row("SELECT id FROM users WHERE login_id = 'teacher1'")
    cls = row("SELECT id FROM classes WHERE teacher_id = ? AND class_no = 2", teacher["id"]) if teacher else None
    s = {i: (row("SELECT id FROM users WHERE login_id = ?", f"student{i}") or {}).get("id") for i in (1, 2, 3)}
    if not (cls and all(s.values())):
        return
    cid, tid = cls["id"], teacher["id"]
    script = [
        (1, [("s", "선생님 저 내일 병원 가서 1교시 늦을 것 같아요", 30), ("t", "알겠어요. 부모님께서 알림장으로도 남겨 주세요.", 29.5), ("s", "네 감사합니다!", 29.4)]),
        (2, [("s", "선생님 모둠 활동에서 지호가 자꾸 장난쳐서 속상해요. 진짜 꼴보기 싫어요", 52), ("t", "속상했겠어요. 내일 쉬는 시간에 같이 이야기해 봐요.", 51), ("s", "네...", 50.8), ("s", "선생님 오늘 모둠 자리 바뀌었어요 고맙습니다", 3), ("t", "잘 지내 보자. 불편하면 또 말해 줘요.", 2.8)]),
        (3, [("s", "독서록 어디에 내요?", 5), ("t", "교실 앞 바구니에 넣으면 돼요.", 4.9)]),
    ]
    with tx() as c:
        for i, msgs in script:
            for who, body, hrs in msgs:
                if who == "s":
                    shown, n = mask_text(body)
                    c.execute("INSERT INTO dm_messages (class_id, student_id, sender_id, body, body_masked, masked_count, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (cid, s[i], s[i], body, shown if n else None, n, ago(hours=hrs)))
                else:
                    c.execute("INSERT INTO dm_messages (class_id, student_id, sender_id, body, sent_at) VALUES (?, ?, ?, ?, ?)", (cid, s[i], tid, body, ago(hours=hrs)))
        c.execute("INSERT INTO demo_meta (key, at) VALUES ('rich_dm_v1', ?)", (now(),))


def seed_talk():
    """톡방 지난 대화 더미 (rich_talk_v1): 학부모별 지난 며칠의 주고받음 · 학생 1:1 지난 대화. 모두 답장/확인이 끝난 것이라 메시지 탭 할 일에는 안 올라온다"""
    if os.environ.get("CUSHION_RICH_DEMO", "on") == "off":
        return
    from app.api.care import mask_text
    with tx() as c:
        c.execute("CREATE TABLE IF NOT EXISTS demo_meta (key TEXT PRIMARY KEY, at TEXT NOT NULL)")
        if c.execute("SELECT 1 FROM demo_meta WHERE key = 'rich_talk_v1'").fetchone():
            return
    teacher = row("SELECT id FROM users WHERE login_id = 'teacher1'")
    cls = row("SELECT id FROM classes WHERE teacher_id = ? AND class_no = 2", teacher["id"]) if teacher else None
    p = {i: (row("SELECT id FROM users WHERE login_id = ?", f"parent{i}") or {}).get("id") for i in range(1, 7)}
    s = {i: (row("SELECT id FROM users WHERE login_id = ?", f"student{i}") or {}).get("id") for i in (1, 2, 3)}
    if not (cls and all(p.values()) and all(s.values())):
        return
    cid, tid = cls["id"], teacher["id"]

    def talk(parent, text, mtype, days, reply=None, gap=1.5, done=False):
        t = ago(days=days)
        with tx() as c:
            mid = c.execute("INSERT INTO messages (parent_id, teacher_id, class_id, original_text, received_at, original_hash, msg_type) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (parent, tid, cid, text, t, hashlib.sha256((text + t).encode()).hexdigest(), mtype)).lastrowid
        run_analysis(mid)
        with tx() as c:
            if reply:
                rt = ago(days=days, hours=-gap)
                c.execute("INSERT INTO replies (message_id, teacher_id, body, sent_at) VALUES (?, ?, ?, ?)", (mid, tid, reply, rt))
                c.execute("UPDATE messages SET teacher_state = 'replied', read_at = ? WHERE id = ?", (rt, mid))
            else:
                c.execute("UPDATE messages SET teacher_state = 'read', read_at = ?, done_at = ? WHERE id = ?", (t, ago(days=days, hours=-gap) if done else None, mid))

    talk(p[1], "선생님, 민서가 요즘 학교 이야기를 잘 안 해요. 학교에서는 어떤가요?", "counsel", 6, "민서는 쉬는 시간에 친구들과 잘 지내고 있어요. 수업 시간에도 발표를 곧잘 한답니다.")
    talk(p[1], "안심이 되네요. 감사합니다 선생님!", "other", 5.8, done=True)
    talk(p[1], "다음 주 월요일 준비물이 어떻게 되나요?", "study", 4, "알림장에 올려 둘게요. 색연필과 가위만 챙겨 주세요.")
    talk(p[2], "하윤이가 어제부터 감기 기운이 있어서 오늘 체육은 쉬게 해 주세요.", "absence", 5, "네 알겠습니다. 교실에서 쉬도록 할게요.")
    talk(p[2], "내일 현장체험학습 신청서는 어디에 내나요?", "life", 3.2, "신청서는 앱의 승인 탭에서 바로 낼 수 있어요.")
    talk(p[3], "선생님, 서연이가 급식에 편식이 심한데 학교에서 도와주실 수 있을까요?", "life", 7, "조금씩 시도해 보도록 격려할게요. 억지로 먹이지는 않을게요.")
    talk(p[3], "감사합니다. 집에서도 같이 노력해 볼게요.", "other", 6.8, done=True)
    talk(p[4], "서준이 학원 때문에 금요일은 일찍 하교해야 해요.", "absence", 6, "알겠습니다. 출결 알리기로 남겨 주세요.")
    talk(p[4], "선생님 서준이가 시력 검사를 받아 봐야 할 것 같아요.", "life", 3.5, "네, 오늘 시력 검사 결과를 알림장으로 알려 드릴게요.")
    talk(p[5], "하은이 생일 파티 초대장을 반에 돌려도 될까요?", "other", 6.5, "교실에서는 어려워요. 개별로 전달해 주세요.")
    talk(p[5], "알겠습니다. 이해해 주셔서 감사해요.", "other", 6.4, done=True)
    talk(p[6], "지호가 방과후 수업에 가기 싫다고 해서 고민이에요.", "counsel", 5, "이번 주 지호와 먼저 이야기해 보겠습니다. 상담 기간에 자세히 나눠요.")
    talk(p[6], "선생님 지호 약 먹는 시간 때문에 점심시간 후에 보건실에 보내 주세요.", "life", 3, "네, 점심 후 보건실로 가도록 챙길게요.")

    older = [
        (1, [("s", "선생님 어제 낸 수학 숙제 틀린 곳 알려 주세요", 80), ("t", "오늘 알림장 확인하고 쉬는 시간에 나한테 오세요.", 79.5), ("s", "네!", 79.4)]),
        (2, [("s", "선생님 이번 체육 시간에 피구해요?", 76), ("t", "날씨 좋으면 하자.", 75.5), ("s", "야호 신난다", 75.4), ("s", "저 줄넘기 잘 못해서 걱정돼요", 56), ("t", "연습하면 늘어요. 쉬는 시간에 같이 해 봐요.", 55)]),
        (3, [("s", "선생님 도서관 책 언제까지 반납이에요", 100), ("t", "다음 주 수요일까지예요.", 99)]),
    ]
    with tx() as c:
        for i, msgs in older:
            for who, body, hrs in msgs:
                if who == "s":
                    shown, n = mask_text(body)
                    c.execute("INSERT INTO dm_messages (class_id, student_id, sender_id, body, body_masked, masked_count, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (cid, s[i], s[i], body, shown if n else None, n, ago(hours=hrs)))
                else:
                    c.execute("INSERT INTO dm_messages (class_id, student_id, sender_id, body, sent_at) VALUES (?, ?, ?, ?, ?)", (cid, s[i], tid, body, ago(hours=hrs)))
        c.execute("INSERT INTO demo_meta (key, at) VALUES ('rich_talk_v1', ?)", (now(),))


def seed_unify():
    """학생 · 학부모 · 교사 화면의 인물을 맞춘다 (rich_unify_v1): 반 아이 6명 = 학부모 6명의 자녀 = 학생 계정 6개.
    학생 이름은 학부모 성을 따른다 (student1 정서준 ← parent4 정수빈 …). 새 학생 student4~6은 민서 · 하윤 · 서연."""
    if os.environ.get("CUSHION_RICH_DEMO", "on") == "off":
        return
    from app.api.care import mask_text
    with tx() as c:
        c.execute("CREATE TABLE IF NOT EXISTS demo_meta (key TEXT PRIMARY KEY, at TEXT NOT NULL)")
        if c.execute("SELECT 1 FROM demo_meta WHERE key = 'rich_unify_v1'").fetchone():
            return
    teacher = row("SELECT id, school_id FROM users WHERE login_id = 'teacher1'")
    cls = row("SELECT id FROM classes WHERE teacher_id = ? AND class_no = 2", teacher["id"]) if teacher else None
    if not cls:
        return
    cid, tid = cls["id"], teacher["id"]
    names = {1: "정서준", 2: "오하은", 3: "강지호", 4: "박민서", 5: "최하윤", 6: "한서연"}
    with tx() as c:
        for i, name in names.items():
            u = c.execute("SELECT id FROM users WHERE login_id = ?", (f"student{i}",)).fetchone()
            if u:
                c.execute("UPDATE users SET name = ? WHERE id = ?", (name, u[0]))
                continue
            uid = c.execute("INSERT INTO users (role, name, school_id, login_id, password_hash, created_at) VALUES ('student', ?, ?, ?, ?, ?)",
                            (name, teacher["school_id"], f"student{i}", hash_pw(DEMO_PW), now())).lastrowid
            c.execute("INSERT INTO class_members (class_id, user_id, member_role, joined_at) VALUES (?, ?, 'student', ?)", (cid, uid, now()))
    s = {i: row("SELECT id FROM users WHERE login_id = ?", f"student{i}")["id"] for i in (4, 5, 6)}
    script = [
        (4, [("s", "선생님 저 내일 짝이랑 자리 바뀌는 거예요?", 8), ("t", "응, 내일 아침 조회 때 새 자리 알려 줄게요.", 7.5), ("s", "네 좋아요!", 7.4)]),
        (5, [("s", "선생님 오늘 체육 못 하고 교실에서 쉬어도 돼요?", 30), ("t", "감기 기운 있다고 들었어요. 교실에서 쉬어요.", 29)]),
        (6, [("s", "선생님 급식에 당근 안 먹어도 돼요?", 54), ("t", "한 입만 먹어 보고 남겨도 괜찮아요.", 53), ("s", "네 한 입 먹어 볼게요", 52.8)]),
    ]
    with tx() as c:
        for i, msgs in script:
            for who, body, hrs in msgs:
                if who == "s":
                    shown, n = mask_text(body)
                    c.execute("INSERT INTO dm_messages (class_id, student_id, sender_id, body, body_masked, masked_count, sent_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (cid, s[i], s[i], body, shown if n else None, n, ago(hours=hrs)))
                else:
                    c.execute("INSERT INTO dm_messages (class_id, student_id, sender_id, body, sent_at) VALUES (?, ?, ?, ?, ?)", (cid, s[i], tid, body, ago(hours=hrs)))
        for who, body, hrs in ((s[4], "저도 색연필 가져왔어요!", 7.7), (s[5], "내일 체육복 입고 오면 되죠?", 6.1), (s[6], "독서록 금요일까지 맞죠?", 26.9)):
            c.execute("INSERT INTO room_messages (class_id, sender_id, body, sent_at) VALUES (?, ?, ?, ?)", (cid, who, body, ago(hours=hrs)))
        c.execute("INSERT INTO demo_meta (key, at) VALUES ('rich_unify_v1', ?)", (now(),))


seed()
seed_chat()
seed_dm()
seed_talk()
seed_unify()
