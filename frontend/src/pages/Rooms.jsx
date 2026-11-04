// E1 반 톡방 목록 · E2/E4 참여 코드 시트 · E3/F3 반 단체 톡방 (교사 · 학생 같은 화면)
import { useEffect, useRef, useState } from 'react'
import { api, usePoll, when } from '../api.js'
import { Btn, Composer, CushionNote, Header, Ic, Sheet, Sticker } from '../components/ui.jsx'
import { SectionHead } from './TeacherHome.jsx'

export function TeacherRooms({ me, onChat, title = '반 톡방', extra }) {
  const [rooms, setRooms] = useState([])
  const [pick, setPick] = useState({ grade: 3, class_no: 1 })
  const [room, setRoom] = useState(null)
  const [fresh, setFresh] = useState(null) // E2: 방금 만든 반의 첫 코드
  const [err, setErr] = useState(null)
  usePoll(async () => setRooms((await api('/teacher/rooms')).rooms), [])
  useEffect(() => { onChat?.(!!room) }, [room]) // eslint-disable-line react-hooks/exhaustive-deps  (채팅 중엔 하단바를 숨김)
  if (room) return <RoomChat classId={room} userId={me.id} teacher onBack={() => setRoom(null)} />
  const openRoom = async () => {
    setErr(null)
    try {
      const r = await api('/teacher/rooms', { method: 'POST', body: pick })
      r.created ? setFresh({ ...r, ...pick }) : setRoom(r.class_id)
    } catch (e) { setErr(e.message) }
  }
  return (
    <div className="app">
      <SectionHead title={title} />
      <div className="page tight" style={{ paddingTop: 6 }}>
        <div className="band"><span>반 톡방</span></div>
        {rooms.length > 0 && (
          <div className="ls">
            {rooms.map((r) => (
              <button key={r.class_id} className="li" onClick={() => setRoom(r.class_id)}>
                <span className="mbadge">{r.grade}-{r.class_no}</span>
                <div className="g"><b>{r.grade}학년 {r.class_no}반 단체 톡방</b><p>학생 {r.student_count}명{r.last_at ? ` · ${when(r.last_at)}` : ''}</p></div>
                <span className="go">›</span>
              </button>
            ))}
          </div>
        )}
        <div className="band"><span>반 톡방 열기</span></div>
        <div className="picks" style={{ padding: '4px 0' }}>
          <select className="sel" value={pick.grade} onChange={(e) => setPick({ ...pick, grade: +e.target.value })} aria-label="학년">
            {[1, 2, 3, 4, 5, 6].map((g) => <option key={g} value={g}>{g}학년</option>)}
          </select>
          <select className="sel" value={pick.class_no} onChange={(e) => setPick({ ...pick, class_no: +e.target.value })} aria-label="반">
            {Array.from({ length: 15 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}반</option>)}
          </select>
          <button className="btn b-sky sm flat" style={{ height: 40 }} onClick={openRoom}>열기</button>
        </div>
        {err && <p className="err">{err}</p>}
        {extra}
      </div>
      {fresh && (
        <CodeSheet title={`${fresh.grade}학년 ${fresh.class_no}반 톡방 생성`} code={fresh.join_code} onClose={() => setFresh(null)}>
          <Btn onClick={() => { setFresh(null); setRoom(fresh.class_id) }}>톡방으로 가기</Btn>
        </CodeSheet>
      )}
    </div>
  )
}

const left = (exp) => {
  const m = Math.max(0, Math.round((new Date(exp) - Date.now()) / 60000))
  return m === 0 ? '만료됨' : `${Math.floor(m / 60)}시간 ${m % 60}분`
}

function CodeSheet({ title, code, onClose, children }) {
  const [copied, setCopied] = useState(false)
  return (
    <Sheet onClose={onClose}>
      <h3>{title}</h3>
      <div className="code">{code.code.slice(0, 3)} {code.code.slice(3)}</div>
      <p className="cap center">남은 시간 <b>{left(code.expires_at)}</b></p>
      <Btn kind="white" onClick={() => navigator.clipboard?.writeText(code.code).then(() => setCopied(true))}>{copied ? '복사됨' : '코드 복사'}</Btn>
      {children}
    </Sheet>
  )
}

// 계정 메뉴에서 바로 여는 참여 코드 (보기 · 새 코드 받기)
export function JoinCodeSheet({ classId, name, onClose }) {
  const [code, setCode] = useState(null)
  useEffect(() => {
    api(`/teacher/rooms/${classId}/join-code`).then(setCode).catch(() => setCode({ code: '------', expires_at: new Date().toISOString(), expired: true }))
  }, [classId])
  const renew = async () => setCode(await api(`/teacher/rooms/${classId}/join-code`, { method: 'POST' }))
  if (!code) return null
  return <CodeSheet title={`${name} 참여 코드`} code={code} onClose={onClose}><Btn onClick={renew}>새 코드 받기</Btn></CodeSheet>
}

// ───────── 반 톡방 채팅 (카카오 · 텔레그램 · 인스타그램에서 가져온 최소 기능) ─────────
// 날짜 구분선 · 프로필 · 연속 묶음 · 시간 · 답장(인용) · 하트(두 번 탭) · 상단 고정 공지(담임) · 담임 표시
const clock = (iso) => new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false })
const dayKey = (iso) => new Date(iso).toDateString()
const dayLabel = (iso) => { const d = new Date(iso); return `${d.getMonth() + 1}월 ${d.getDate()}일 (${'일월화수목금토'[d.getDay()]})` }
const close = (a, b) => a && b && a.sender_id === b.sender_id && dayKey(a.sent_at) === dayKey(b.sent_at) && Math.abs(Date.parse(b.sent_at) - Date.parse(a.sent_at)) < 5 * 60e3

export function RoomChat({ classId, userId, teacher, onBack, onOut }) {
  const [info, setInfo] = useState(null)
  const [msgs, setMsgs] = useState([])
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [sel, setSel] = useState(null) // 눌러서 고른 메시지 (하트 · 답장 · 고정)
  const [reply, setReply] = useState(null)
  const [pinOpen, setPinOpen] = useState(false)
  const [menu, setMenu] = useState(false)
  const [members, setMembers] = useState([])
  const [code, setCode] = useState(null)
  const end = useRef(null)
  const pull = async () => { const r = await api(`/rooms/${classId}/messages`); setInfo(r); setMsgs(r.messages) }
  usePoll(pull, [classId], 4000)
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs.length])
  const send = async () => {
    setBusy(true)
    try { await api(`/rooms/${classId}/messages`, { method: 'POST', body: { body, reply_to: reply?.id ?? null } }); setBody(''); setReply(null); await pull() } finally { setBusy(false) }
  }
  const heart = async (m) => { await api(`/rooms/${classId}/messages/${m.id}/heart`, { method: 'POST' }); pull() }
  const pin = async (m) => { await api(`/rooms/${classId}/pin`, { method: 'POST', body: { message_id: info?.pin?.id === m.id ? null : m.id } }); setSel(null); pull() }
  const openMenu = async () => { setMenu(true); setMembers((await api(`/rooms/${classId}/members`)).members) }
  const showCode = async () => { setMenu(false); setCode(await api(`/teacher/rooms/${classId}/join-code`).catch(() => ({ code: '------', expires_at: new Date().toISOString(), expired: true }))) }
  const renew = async () => setCode(await api(`/teacher/rooms/${classId}/join-code`, { method: 'POST' }))

  return (
    <div className="app room">
      <Header onBack={onBack} title={`${info?.class_name || ''} 단체 톡방`} sub={`참여 ${(info?.member_count ?? 0) + 1}명`}
        right={<button className="menu" onClick={openMenu} aria-label="메뉴"><Ic name="메뉴" size={22} /></button>} />
      {info?.pin && (
        <button className="pinbar" onClick={() => setPinOpen(!pinOpen)}>
          <Ic name="고정" size={16} />
          <span className={pinOpen ? '' : 'one'}><b>공지</b> {info.pin.body}</span>
          <Ic name="펼침" size={16} />
        </button>
      )}
      <div className="chatbox" onClick={() => setSel(null)}>
        {msgs.map((m, i) => {
          const prev = msgs[i - 1], next = msgs[i + 1]
          const mine = m.sender_id === userId
          const isT = m.sender_role === 'teacher'
          const newDay = !prev || dayKey(prev.sent_at) !== dayKey(m.sent_at)
          const head = !close(prev, m)
          const last = !close(m, next)
          return (
            <div key={m.id} style={{ display: 'contents' }}>
              {newDay && <div className="cday">{dayLabel(m.sent_at)}</div>}
              <div className={`crow${mine ? ' me' : ''}`}>
                {!mine && (head ? <span className={`cav${isT ? ' tch' : ''}`}>{m.sender_name[0]}</span> : <span className="cspace" />)}
                <div className="ccol">
                  {!mine && head && <span className="cname">{m.sender_name}{isT && <span className="tchip">담임</span>}</span>}
                  {m.reply && <span className="mq">{m.reply.sender_name} · {m.reply.body}</span>}
                  <button className={`msg${isT ? ' tch' : ''}`} onClick={(e) => { e.stopPropagation(); setSel(sel === m.id ? null : m.id) }} onDoubleClick={() => heart(m)}>{m.body}</button>
                  {m.hearts > 0 && <button className={`rxpill${m.my_heart ? ' on' : ''}`} onClick={() => heart(m)} aria-label="하트"><Ic name="하트" size={12} fill={m.my_heart ? 'currentColor' : 'none'} />{m.hearts}</button>}
                  {sel === m.id && (
                    <div className="ctools" onClick={(e) => e.stopPropagation()}>
                      <button onClick={() => { heart(m); setSel(null) }} aria-label="하트"><Ic name="하트" size={16} fill={m.my_heart ? 'currentColor' : 'none'} /></button>
                      <button onClick={() => { setReply(m); setSel(null) }} aria-label="답장"><Ic name="답장" size={16} /></button>
                      {teacher && <button onClick={() => pin(m)} aria-label="공지 고정"><Ic name="고정" size={16} fill={info?.pin?.id === m.id ? 'currentColor' : 'none'} /></button>}
                    </div>
                  )}
                </div>
                {last && <span className="ctm">{clock(m.sent_at)}</span>}
              </div>
            </div>
          )
        })}
        <div ref={end} />
      </div>
      <Composer placeholder="메시지" value={body} onChange={setBody} onSend={send} busy={busy}>
        {reply && <div className="replyto"><Ic name="답장" size={14} /><span>{reply.sender_name} · {reply.body}</span><button onClick={() => setReply(null)} aria-label="답장 취소">✕</button></div>}
      </Composer>
      {menu && (
        <Sheet onClose={() => setMenu(false)}>
          <h3 style={{ textAlign: 'center' }}>참여 {members.length}명</h3>
          <div className="ls" style={{ margin: '0 -20px' }}>
            {teacher && <button className="li" style={{ padding: '14px 20px' }} onClick={showCode}><div className="g"><b>참여 코드</b></div><span className="go">›</span></button>}
            {members.map((mb) => (
              <div key={`${mb.role}${mb.name}`} className="li" style={{ padding: '12px 20px' }}><span className={`cav${mb.role === 'teacher' ? ' tch' : ''}`}>{mb.name[0]}</span><div className="g"><b>{mb.name}</b></div>{mb.role === 'teacher' && <span className="tchip">담임</span>}</div>))}
          </div>
        </Sheet>
      )}
      {code && (
        <CodeSheet title={`${info?.class_name} 참여 코드`} code={code} onClose={() => setCode(null)}>
          <Btn onClick={renew}>새 코드 받기</Btn>
        </CodeSheet>
      )}
    </div>
  )
}

// ───────── 교사 · 학생 1:1 톡방 (학생이 보낸 글은 AI가 거친 표현을 가린다. 담임은 눌러서 원문을 볼 수 있다) ─────────
export function DmList({ classId, teacher, onOpen }) {
  const [threads, setThreads] = useState([])
  usePoll(async () => {
    if (!classId) return
    setThreads(teacher ? (await api(`/teacher/talk?class_id=${classId}`)).threads
      : (await api(`/rooms/${classId}/dm`)).threads.map((t) => ({ ...t, kind: 'student', key: t.student_id })))
  }, [classId, teacher], 8000)
  return (
    <>
      <div className="band"><span>{teacher ? '학부모 · 학생' : '선생님'}</span><span>{threads.length}</span></div>
      <div className="ls">
        {threads.map((t) => (
          <button key={`${t.kind}${t.key}`} className="li" onClick={() => onOpen(t.kind === 'parent' ? { parent: t.key, title: t.title } : { dm: t.key, title: teacher ? t.title : `${t.title} 선생님` })}>
            <span className={`cav${t.kind === 'parent' ? ' par' : teacher ? '' : ' tch'}`}>{t.title[0]}</span>
            <div className="g"><b>{teacher ? t.title : `${t.title} 선생님`}{t.kind === 'student' && teacher && <span className="tchip">학생</span>}</b><p>{t.last || ' '}</p></div>
            <span className="t">{t.last_at ? when(t.last_at) : ''}{t.unread > 0 && <i className="rb">{t.unread}</i>}</span>
          </button>
        ))}
      </div>
    </>
  )
}

// 학부모와 주고받은 기록 (학부모 글은 쿠션이가 가린 채로, 담임은 눌러서 원문)
export function ParentChat({ classId, parentId, title, onBack }) {
  const [info, setInfo] = useState(null)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [orig, setOrig] = useState(null)
  const end = useRef(null)
  const pull = async () => setInfo(await api(`/teacher/talk/parent/${parentId}?class_id=${classId}`))
  usePoll(pull, [classId, parentId], 5000)
  const msgs = info?.messages || []
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs.length])
  const send = async () => {
    setBusy(true)
    try { await api(`/teacher/messages/${info.reply_to}/replies`, { method: 'POST', body: { body } }); setBody(''); await pull() } finally { setBusy(false) }
  }
  return (
    <div className="app room">
      <Header onBack={onBack} title={title || info?.title || ''} sub="학부모" />
      <div className="chatbox">
        {msgs.map((m, i) => {
          const prev = msgs[i - 1], next = msgs[i + 1]
          const mine = m.from === 'teacher'
          const newDay = !prev || dayKey(prev.sent_at) !== dayKey(m.sent_at)
          const head = !prev || prev.from !== m.from || dayKey(prev.sent_at) !== dayKey(m.sent_at)
          const last = !next || next.from !== m.from || !close({ sender_id: m.from, sent_at: m.sent_at }, { sender_id: next.from, sent_at: next.sent_at })
          const open = orig === m.id && m.original
          return (
            <div key={m.id} style={{ display: 'contents' }}>
              {newDay && <div className="cday">{dayLabel(m.sent_at)}</div>}
              <div className={`crow${mine ? ' me' : ''}`}>
                {!mine && (head ? <span className="cav par">{(title || '보')[0]}</span> : <span className="cspace" />)}
                <div className="ccol">
                  {!mine && head && <span className="cname">{title}</span>}
                  {m.cushion
                    ? <CushionNote size={40} summary={m.body} original={m.original} open={!!open} onToggle={() => setOrig(orig === m.id ? null : m.id)} />
                    : <button className="msg" onClick={() => m.original && setOrig(orig === m.id ? null : m.id)}>{open ? m.original : m.segments ? m.segments.map((g, k) => g.mask ? <Sticker key={k} n={g.mask} /> : <span key={k}>{g.t}</span>) : m.body}</button>}
                  {m.done && m.from === 'parent' && <span className="rxpill chk" aria-label="확인"><Ic name="tick" size={12} /></span>}
                  {m.urgent && <span className="maskchip urgchip">긴급</span>}
                  {m.masked_count > 0 && <span className="maskchip">{open ? '원문' : `${m.masked_count}곳 가림`}</span>}
                </div>
                {last && <span className="ctm">{clock(m.sent_at)}</span>}
              </div>
            </div>
          )
        })}
        <div ref={end} />
      </div>
      <Composer placeholder="답장" value={body} onChange={setBody} onSend={send} busy={busy} />
    </div>
  )
}

export function DmChat({ classId, studentId, userId, teacher, title, onBack }) {
  const [msgs, setMsgs] = useState([])
  const [info, setInfo] = useState(null)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [orig, setOrig] = useState(null) // 담임이 원문을 펼친 메시지
  const end = useRef(null)
  const pull = async () => { const r = await api(`/rooms/${classId}/dm/${studentId}/messages`); setInfo(r); setMsgs(r.messages) }
  usePoll(pull, [classId, studentId], 4000)
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs.length])
  const send = async () => {
    setBusy(true)
    try { await api(`/rooms/${classId}/dm/${studentId}/messages`, { method: 'POST', body: { body } }); setBody(''); await pull() } finally { setBusy(false) }
  }
  return (
    <div className="app room">
      <Header onBack={onBack} title={title || info?.title || ''} sub={teacher ? '학생' : '담임 선생님'} />
      <div className="chatbox">
        {msgs.map((m, i) => {
          const prev = msgs[i - 1], next = msgs[i + 1]
          const mine = m.sender_id === userId
          const isT = m.sender_role === 'teacher'
          const newDay = !prev || dayKey(prev.sent_at) !== dayKey(m.sent_at)
          const head = !close(prev, m)
          const last = !close(m, next)
          const open = orig === m.id && m.original
          return (
            <div key={m.id} style={{ display: 'contents' }}>
              {newDay && <div className="cday">{dayLabel(m.sent_at)}</div>}
              <div className={`crow${mine ? ' me' : ''}`}>
                {!mine && (head ? <span className={`cav${isT ? ' tch' : ''}`}>{m.sender_name[0]}</span> : <span className="cspace" />)}
                <div className="ccol">
                  {!mine && head && <span className="cname">{m.sender_name}{isT && <span className="tchip">담임</span>}</span>}
                  <button className={`msg${isT ? ' tch' : ''}`} onClick={() => teacher && m.original && setOrig(orig === m.id ? null : m.id)}>{open ? m.original : m.segments ? m.segments.map((g, k) => g.mask ? <Sticker key={k} n={g.mask} /> : <span key={k}>{g.t}</span>) : m.body}</button>
                  {m.masked_count > 0 && <span className="maskchip">{open ? '원문' : `${m.masked_count}곳 가림`}</span>}
                </div>
                {last && <span className="ctm">{clock(m.sent_at)}</span>}
              </div>
            </div>
          )
        })}
        <div ref={end} />
      </div>
      <Composer placeholder="메시지" value={body} onChange={setBody} onSend={send} busy={busy} />
    </div>
  )
}

// 톡방 탭 (교사): 상단 반 톡방, 하단 학생별 1:1 톡방
export function TeacherTalk({ me, classId, initial, onChat }) {
  const [dm, setDm] = useState(initial || null)
  const [roomOpen, setRoomOpen] = useState(false)
  useEffect(() => { onChat?.(roomOpen || !!dm) }, [roomOpen, dm]) // eslint-disable-line react-hooks/exhaustive-deps
  if (dm?.parent) return <ParentChat classId={classId} parentId={dm.parent} title={dm.title} onBack={() => setDm(null)} />
  if (dm) return <DmChat classId={classId} studentId={dm.dm} userId={me.id} teacher title={dm.title} onBack={() => setDm(null)} />
  return <TeacherRooms me={me} title="톡방" onChat={setRoomOpen} extra={<DmList classId={classId} teacher onOpen={setDm} />} />
}

// 톡방 탭 (학생): 상단 반 톡방, 하단 담임 선생님과의 1:1 톡방
export function StudentTalk({ me, classId, initial, onChat }) {
  const [view, setView] = useState(initial || null) // null · 'room' · { dm, title }
  const [info, setInfo] = useState(null)
  usePoll(async () => setInfo(await api(`/rooms/${classId}/messages`)), [classId], 15000)
  useEffect(() => { onChat?.(!!view) }, [view]) // eslint-disable-line react-hooks/exhaustive-deps
  if (view === 'room') return <RoomChat classId={classId} userId={me.id} onBack={() => setView(null)} />
  if (view?.dm) return <DmChat classId={classId} studentId={view.dm} userId={me.id} title={view.title} onBack={() => setView(null)} />
  const m = info?.class_name?.match(/(\d+)학년 (\d+)반/)
  return (
    <div className="app">
      <SectionHead title="톡방" />
      <div className="page tight" style={{ paddingTop: 6 }}>
        <div className="band"><span>반 톡방</span></div>
        <div className="ls">
          <button className="li" onClick={() => setView('room')}>
            <span className="mbadge">{m ? `${m[1]}-${m[2]}` : ''}</span>
            <div className="g"><b>{info?.class_name} 단체 톡방</b><p>참여 {(info?.member_count ?? 0) + 1}명</p></div><span className="go">›</span>
          </button>
        </div>
        <DmList classId={classId} onOpen={setView} />
      </div>
    </div>
  )
}
