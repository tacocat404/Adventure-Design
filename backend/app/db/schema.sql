-- 이 파일은 docs/05_데이터/DB설계_쿠션톡_261017.html의 07 생성문을 옮긴 것.
-- 고칠 때는 DB 설계 문서와 함께 고친다.
-- 쿠션톡 DB (SQLite) · 26.10.17 · 11.02 보완
PRAGMA foreign_keys = ON;

CREATE TABLE schools (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE TABLE users (
  id             INTEGER PRIMARY KEY,
  role           TEXT NOT NULL CHECK (role IN ('parent','teacher','admin','student')),
  name           TEXT NOT NULL,
  school_id      INTEGER NOT NULL REFERENCES schools(id),
  login_id       TEXT UNIQUE,            -- 학생은 NULL (코드와 이름으로 참여)
  password_hash  TEXT,                   -- 해시만 저장 · 학생은 NULL
  created_at     TEXT NOT NULL,
  CHECK (role = 'student' OR (login_id IS NOT NULL AND password_hash IS NOT NULL))
);
CREATE INDEX school_search ON schools(name);   -- 학부모 가입: 학교 이름 검색

CREATE TABLE classes (
  id          INTEGER PRIMARY KEY,
  school_id   INTEGER NOT NULL REFERENCES schools(id),
  teacher_id  INTEGER NOT NULL REFERENCES users(id),
  year        INTEGER NOT NULL,
  grade       INTEGER NOT NULL CHECK (grade BETWEEN 1 AND 6),
  class_no    INTEGER NOT NULL,
  created_at  TEXT NOT NULL,
  UNIQUE (school_id, year, grade, class_no)
);

CREATE TABLE join_codes (
  id          INTEGER PRIMARY KEY,
  class_id    INTEGER NOT NULL REFERENCES classes(id),
  code        TEXT NOT NULL UNIQUE,      -- 막힌 코드까지 전체에서 하나 · 다시 쓰지 않음
  issued_by   INTEGER NOT NULL REFERENCES users(id),
  issued_at   TEXT NOT NULL,
  expires_at  TEXT NOT NULL,             -- issued_at + 24시간
  revoked_at  TEXT                       -- 새 코드를 받으면 채움
);
-- 살아 있는 코드: 반마다 하나 (새 코드를 받기 전에 이전 행 revoked_at을 채움)
CREATE UNIQUE INDEX one_live_code_per_class ON join_codes(class_id) WHERE revoked_at IS NULL;

CREATE TABLE class_members (
  id            INTEGER PRIMARY KEY,
  class_id      INTEGER NOT NULL REFERENCES classes(id),
  user_id       INTEGER NOT NULL REFERENCES users(id),
  member_role   TEXT NOT NULL CHECK (member_role IN ('student','parent')),
  child_name    TEXT,
  join_code_id  INTEGER REFERENCES join_codes(id),
  joined_at     TEXT NOT NULL,
  UNIQUE (class_id, user_id)
);

CREATE TABLE room_messages (
  id         INTEGER PRIMARY KEY,
  class_id   INTEGER NOT NULL REFERENCES classes(id),
  sender_id  INTEGER NOT NULL REFERENCES users(id),
  body       TEXT NOT NULL,
  sent_at    TEXT NOT NULL
);

CREATE TABLE messages (
  id               INTEGER PRIMARY KEY,
  parent_id        INTEGER NOT NULL REFERENCES users(id),
  teacher_id       INTEGER NOT NULL REFERENCES users(id),
  class_id         INTEGER NOT NULL REFERENCES classes(id),
  original_text    TEXT NOT NULL,        -- 잠금
  received_at      TEXT NOT NULL,        -- 잠금 · 서버 시간
  original_hash    TEXT NOT NULL,        -- 잠금 · SHA-256(original_text || received_at)
  analysis_status  TEXT NOT NULL DEFAULT 'pending' CHECK (analysis_status IN ('pending','done','failed')),
  category         TEXT CHECK (category IN ('urgent','threat','normal')),
  msg_type         TEXT NOT NULL CHECK (msg_type IN ('counsel','absence','seating','study','life','other')),  -- 학부모가 고름
  due_date         TEXT,                 -- 학부모가 고른 답장 기한
  used_suggestion  INTEGER NOT NULL DEFAULT 0 CHECK (used_suggestion IN (0,1)),  -- A5 표시용
  teacher_state    TEXT NOT NULL DEFAULT 'new' CHECK (teacher_state IN ('new','read','replied')),
  read_at          TEXT
);
CREATE INDEX inbox ON messages(teacher_id, category, teacher_state, received_at);

-- 원문 잠금: 고치기 · 지우기 막기
CREATE TRIGGER lock_original BEFORE UPDATE OF original_text, received_at, original_hash ON messages
BEGIN
  SELECT RAISE(ABORT, 'original is locked');
END;
CREATE TRIGGER keep_messages BEFORE DELETE ON messages
BEGIN
  SELECT RAISE(ABORT, 'messages cannot be deleted');
END;

CREATE TABLE analyses (
  message_id     INTEGER PRIMARY KEY REFERENCES messages(id),
  ai_category    TEXT NOT NULL CHECK (ai_category IN ('urgent','threat','normal')),
  urgent_type    TEXT CHECK (urgent_type IN ('school_violence','child_abuse','safety')),
  summary        TEXT NOT NULL,
  requests       TEXT NOT NULL,          -- JSON 배열
  masked_count   INTEGER NOT NULL DEFAULT 0,
  masked_spans   TEXT NOT NULL DEFAULT '[]',  -- JSON [{start, end}]
  threat_reason  TEXT,
  attempts       INTEGER NOT NULL CHECK (attempts BETWEEN 1 AND 2),
  model          TEXT NOT NULL,
  analyzed_at    TEXT NOT NULL
);

CREATE TABLE replies (
  id          INTEGER PRIMARY KEY,
  message_id  INTEGER NOT NULL REFERENCES messages(id),
  teacher_id  INTEGER NOT NULL REFERENCES users(id),
  body        TEXT NOT NULL,
  sent_at     TEXT NOT NULL
);

CREATE TABLE threat_cases (
  id          INTEGER PRIMARY KEY,
  message_id  INTEGER NOT NULL UNIQUE REFERENCES messages(id),
  school_id   INTEGER NOT NULL REFERENCES schools(id),
  status      TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','handled','returned')),
  opened_at   TEXT NOT NULL,
  closed_at   TEXT
);

CREATE TABLE case_actions (
  id           INTEGER PRIMARY KEY,
  case_id      INTEGER NOT NULL REFERENCES threat_cases(id),
  admin_id     INTEGER NOT NULL REFERENCES users(id),
  action_type  TEXT NOT NULL CHECK (action_type IN ('meeting','report_office','report_police','return_normal','other')),
  memo         TEXT,
  created_at   TEXT NOT NULL
);
-- 대응 기록은 덧붙이기만 (11.02 확정)
CREATE TRIGGER append_only_actions BEFORE UPDATE ON case_actions
BEGIN
  SELECT RAISE(ABORT, 'case_actions are append-only');
END;
CREATE TRIGGER keep_actions BEFORE DELETE ON case_actions
BEGIN
  SELECT RAISE(ABORT, 'case_actions cannot be deleted');
END;

CREATE TABLE original_views (
  id          INTEGER PRIMARY KEY,
  message_id  INTEGER NOT NULL REFERENCES messages(id),
  viewer_id   INTEGER NOT NULL REFERENCES users(id),
  via         TEXT NOT NULL CHECK (via IN ('teacher_sheet','urgent_detail','failed_expand','admin_evidence')),
  viewed_at   TEXT NOT NULL
);

CREATE TABLE notifications (
  id          INTEGER PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  kind        TEXT NOT NULL CHECK (kind IN ('new_message','urgent','threat','case_update','reply')),
  ref_type    TEXT NOT NULL CHECK (ref_type IN ('message','case','reply')),
  ref_id      INTEGER NOT NULL,
  created_at  TEXT NOT NULL,
  read_at     TEXT
);
CREATE INDEX unread ON notifications(user_id, read_at);
