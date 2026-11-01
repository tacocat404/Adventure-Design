// E1 반 톡방 목록 · E2/E4 참여 코드 시트 · E3/F3 반 단체 톡방 (교사 · 학생 같은 화면)
import { useState } from 'react'
import { api, usePoll, when } from '../api.js'
import { Btn, Composer, Header, Sheet, Title } from '../components/ui.jsx'

export function TeacherRooms({ me }) {
  const [rooms, setRooms] = useState([])
  const [pick, setPick] = useState({ grade: 3, class_no: 1 })
  const [room, setRoom] = useState(null)
  const [fresh, setFresh] = useState(null) // E2: 방금 만든 반의 첫 코드
  const [err, setErr] = useState(null)
  usePoll(async () => setRooms((await api('/teacher/rooms')).rooms), [])
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
      <Title title="반 톡방" side="개인 메신저 없이 반 학생들과" />
      <div className="page">
        {rooms.length > 0 && <p className="sec">내 반 톡방</p>}
        {rooms.map((r) => (
          <button key={r.class_id} className="chunk row" onClick={() => setRoom(r.class_id)}>
            <span className="av sq">{r.grade}-{r.class_no}</span>
            <span className="grow"><b>{r.grade}학년 {r.class_no}반 단체 톡방</b><span className="cap" style={{ display: 'block' }}>학생 {r.student_count}명{r.last_at ? ` · ${when(r.last_at)}` : ''}</span></span>
            <span style={{ color: 'var(--sub)' }}>›</span>
          </button>
        ))}
        <p className="sec">반 톡방 열기</p>
        <div className="picks">
          <select className="sel" value={pick.grade} onChange={(e) => setPick({ ...pick, grade: +e.target.value })} aria-label="학년">
            {[1, 2, 3, 4, 5, 6].map((g) => <option key={g} value={g}>{g}학년</option>)}
          </select>
          <select className="sel" value={pick.class_no} onChange={(e) => setPick({ ...pick, class_no: +e.target.value })} aria-label="반">
            {Array.from({ length: 15 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}반</option>)}
          </select>
          <button className="btn b-sky sm" style={{ height: 40, boxShadow: '0 3px 0 var(--sky-deep)' }} onClick={openRoom}>열기</button>
        </div>
        {err && <p className="err">{err}</p>}
        <p className="cap">이미 있는 반이면 그 톡방으로 들어가요. 없으면 새로 만들고 참여 코드를 드려요.</p>
      </div>
      {fresh && (
        <CodeSheet title={`${fresh.grade}학년 ${fresh.class_no}반 톡방을 만들었어요`} code={fresh.join_code} onClose={() => setFresh(null)}>
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
      <p className="cap center">학생에게 아래 참여 코드를 알려 주세요.</p>
      <div className="code">{code.code.slice(0, 3)} {code.code.slice(3)}</div>
      <p className="cap center">남은 시간 <b>{left(code.expires_at)}</b> · 참여 코드는 반마다 하나예요</p>
      <Btn kind="white" onClick={() => navigator.clipboard?.writeText(code.code).then(() => setCopied(true))}>{copied ? '복사했어요' : '코드 복사'}</Btn>
      {children}
    </Sheet>
  )
}

export function RoomChat({ classId, userId, teacher, onBack, onOut }) {
  const [info, setInfo] = useState(null)
  const [msgs, setMsgs] = useState([])
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [code, setCode] = useState(null)
  const pull = async () => {
    const after = msgs.length ? `?after_id=${msgs[msgs.length - 1].id}` : ''
    const r = await api(`/rooms/${classId}/messages${after}`)
    setInfo(r)
    if (r.messages.length) setMsgs((old) => [...old, ...r.messages.filter((m) => !old.some((o) => o.id === m.id))])
  }
  usePoll(pull, [classId, msgs.length])
  const send = async () => {
    setBusy(true)
    try { await api(`/rooms/${classId}/messages`, { method: 'POST', body: { body } }); setBody(''); await pull() } finally { setBusy(false) }
  }
  const showCode = async () => setCode(await api(`/teacher/rooms/${classId}/join-code`).catch(() => ({ code: '------', expires_at: new Date().toISOString(), expired: true })))
  const renew = async () => setCode(await api(`/teacher/rooms/${classId}/join-code`, { method: 'POST' }))
  return (
    <div className="app">
      <Header onBack={onBack} title={`${info?.class_name || ''} 단체 톡방`} sub={`${teacher ? '' : '담임 선생님 · '}학생 ${info?.member_count ?? 0}명`}
        right={teacher ? <button className="btn b-white sm" onClick={showCode}>참여 코드</button> : onOut && <button className="cap" onClick={onOut}>나가기</button>} />
      <div className="page tight">
        {teacher && <div className="banner notice">선생님의 개인 메신저 계정은 학생에게 보이지 않아요.</div>}
        {msgs.length === 0 && <p className="cap center">아직 대화가 없어요. 첫 인사를 남겨 보세요.</p>}
        {msgs.map((m) => {
          const mine = m.sender_id === userId
          return (
            <div key={m.id} style={{ display: 'contents' }}>
              {!mine && <p className="who">{m.sender_role === 'teacher' ? '담임 선생님' : m.sender_name}</p>}
              <div className={`bub${mine ? ' me' : ''}`}>{m.body}</div>
            </div>
          )
        })}
      </div>
      <Composer placeholder="메시지를 적어 주세요" value={body} onChange={setBody} onSend={send} busy={busy} />
      {code && (
        <CodeSheet title={`${info?.class_name} 참여 코드`} code={code} onClose={() => setCode(null)}>
          <Btn onClick={renew}>새 코드 받기</Btn>
          <p className="cap center">새 코드를 받으면 지금 코드는 바로 막혀요. 이미 들어온 학생은 그대로예요.</p>
        </CodeSheet>
      )}
    </div>
  )
}
