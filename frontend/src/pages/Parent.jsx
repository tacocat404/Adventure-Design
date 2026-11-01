// A0 선생님 목록 · A1~A5 학부모 작성 · 경고 시트
import { useState } from 'react'
import { api, usePoll, TYPES, when } from '../api.js'
import { Btn, Composer, Cushi, Header, Marked, Sheet, Title } from '../components/ui.jsx'

export default function Parent({ me, onOut }) {
  const [cls, setCls] = useState(null)
  return cls ? <Conversation cls={cls} onBack={() => setCls(null)} /> : <Teachers me={me} onOut={onOut} onOpen={setCls} />
}

function Teachers({ me, onOut, onOpen }) {
  const [data, setData] = useState({ mine: [], others: [] })
  const [pick, setPick] = useState(null)
  const [child, setChild] = useState('')
  const [err, setErr] = useState(null)
  usePoll(async () => setData(await api('/parent/teachers')), [])
  const link = async () => {
    try {
      await api(`/parent/classes/${pick.class_id}/link`, { method: 'POST', body: { child_name: child.trim() } })
      onOpen({ ...pick, child_name: child.trim() })
    } catch (e) { setErr(e.message) }
  }
  const Row = ({ c, onClick }) => (
    <button className="chunk row" onClick={onClick}>
      <span className="av sq">{c.grade}-{c.class_no}</span>
      <span className="grow"><b>{c.grade}학년 {c.class_no}반 {c.teacher_name} 선생님</b>
        {c.child_name && <span className="cap" style={{ display: 'block' }}>{c.child_name}{c.last_at ? ` · ${when(c.last_at)} 대화` : ''}</span>}</span>
      <span style={{ color: 'var(--sub)' }}>›</span>
    </button>
  )
  return (
    <div className="app">
      <Title title="선생님 목록" side={me.school_name || ''} right={<button className="cap" onClick={onOut}>로그아웃</button>} />
      <div className="page tight">
        {data.mine.length > 0 && <p className="sec">내 아이 담임</p>}
        {data.mine.map((c) => <Row key={c.class_id} c={c} onClick={() => onOpen(c)} />)}
        <p className="sec">다른 반</p>
        {data.others.map((c) => <Row key={c.class_id} c={c} onClick={() => { setPick(c); setChild(''); setErr(null) }} />)}
        <p className="cap">처음 연락하는 선생님이면 자녀 이름을 한 번 적어요.</p>
      </div>
      {pick && (
        <Sheet onClose={() => setPick(null)}>
          <h3>{pick.grade}학년 {pick.class_no}반 {pick.teacher_name} 선생님</h3>
          <label className="lbl" htmlFor="child">자녀 이름</label>
          <input id="child" className="field" value={child} onChange={(e) => setChild(e.target.value)} />
          {err && <p className="err">{err}</p>}
          <Btn disabled={!child.trim()} onClick={link}>이 선생님께 연락하기</Btn>
        </Sheet>
      )}
    </div>
  )
}

const PRECHECK_MS = 5000

function Conversation({ cls, onBack }) {
  const [items, setItems] = useState(null)
  const [text, setText] = useState('')
  const [type, setType] = useState('')
  const [due, setDue] = useState('')
  const [stage, setStage] = useState(null) // null · checking · sending
  const [warn, setWarn] = useState(null) // 보내기 전 검사 결과
  const [choice, setChoice] = useState(0)
  const [editing, setEditing] = useState(null) // 직접 고치기: 표시할 구간
  const [sentNote, setSentNote] = useState(false)
  const [err, setErr] = useState(null)
  const load = async () => setItems((await api(`/parent/classes/${cls.class_id}/conversation`)).items)
  usePoll(load, [cls.class_id])

  const send = async (body, used) => {
    setStage('sending'); setWarn(null); setEditing(null)
    try {
      await api('/parent/messages', { method: 'POST', body: { class_id: cls.class_id, text: body, msg_type: type, due_date: due || null, used_suggestion: used } })
      setText(''); setSentNote(true); await load()
    } catch (e) { setErr(e.message) } finally { setStage(null) }
  }
  const check = async () => {
    if (!type) return setErr('요청 유형을 골라 주세요.')
    setErr(null); setStage('checking')
    const timeout = new Promise((r) => setTimeout(() => r(null), PRECHECK_MS))
    const r = await Promise.race([api('/parent/precheck', { method: 'POST', body: { text } }).catch(() => null), timeout])
    if (r?.rough) { setStage(null); setChoice(0); setWarn({ ...r, text }) } else send(text, false) // 5초 넘거나 실패하면 검사 없이 보냄
  }

  return (
    <div className="app">
      <Header onBack={onBack} title={`${cls.grade}학년 ${cls.class_no}반 담임 선생님`} sub="학교 공식 창구 · 쿠션이가 먼저 읽어요" />
      <div className="page tight">
        {items?.length === 0 && <div className="cxr"><Cushi face="hi" size={48} /><div className="say">제가 먼저 읽고 선생님께 전해 드려요.</div></div>}
        {items?.map((m) => m.kind === 'reply'
          ? <div key={`r${m.id}`} className="bub">{m.text}<div className="cap">{when(m.at)}</div></div>
          : <div key={`m${m.id}`} style={{ display: 'contents' }}>
              <div className="bub me">{m.text}</div>
              <div className="meta">{m.used_suggestion && <span className="tag tg-line">제안 문장으로 보냄</span>}<span>{TYPES[m.msg_type]} · {when(m.at)}</span></div>
            </div>)}
        {sentNote && <div className="banner notice">요청 내용은 빠짐없이 선생님께 전해져요.</div>}
      </div>
      <Composer placeholder="선생님께 전할 내용을 적어 주세요" value={text} onChange={setText} onSend={check} busy={!!stage}>
        {stage === 'checking' && <div className="row cap"><Cushi face="read" size={30} />쿠션이가 표현을 살펴보고 있어요</div>}
        {editing && <><div className="cap">표시된 부분을 고쳐 다시 보내 주세요</div><div className="quote"><Marked text={editing.text} spans={editing.spans} /></div></>}
        {err && <p className="err" role="alert">{err}</p>}
        <div className="picks">
          <select className="sel" value={type} onChange={(e) => setType(e.target.value)} aria-label="요청 유형">
            <option value="">유형 고르기</option>
            {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input className="sel" type="date" value={due} onChange={(e) => setDue(e.target.value)} aria-label="답장 기한 (선택)" title="답장 기한 (선택)" />
        </div>
      </Composer>

      {warn && (
        <Sheet warn onClose={() => setWarn(null)}>
          <h3>이 표현은 교권 침해로 기록될 수 있어요</h3>
          <div className="quote"><Marked text={warn.text} spans={warn.spans} /></div>
          {warn.suggestions.map((s, i) => (
            <button key={i} className={`opt${choice === i ? ' on' : ''}`} onClick={() => setChoice(i)}>
              {i === 0 && <span className="tag rec">쿠션이 추천</span>}
              <span className="radio" /><span>{s}</span>
            </button>
          ))}
          {warn.keeps.length > 0 && (
            <div className="tags">{warn.keeps.map((k) => <span key={k} className="tag tg-mint">✓ {k}</span>)}<span className="cap">그대로 전해져요</span></div>
          )}
          {warn.suggestions.length > 0 && <Btn onClick={() => send(warn.suggestions[choice], true)}>바꾼 문장으로 보내기</Btn>}
          <div className="two">
            <Btn kind="white" onClick={() => { setEditing(warn); setWarn(null) }}>직접 고치기</Btn>
            <button className="btn b-ghost" onClick={() => send(warn.text, false)}>그대로 보내기</button>
          </div>
        </Sheet>
      )}
    </div>
  )
}
