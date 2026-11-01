// G1 로그인 · G2 학부모 가입 · F1/F2 반 톡방 참여(학생)
import { useState } from 'react'
import { api } from '../api.js'
import { Btn, Cushi, Header, Title } from '../components/ui.jsx'

export default function Login({ onIn }) {
  const [mode, setMode] = useState('login')
  if (mode === 'signup') return <Signup onIn={onIn} onBack={() => setMode('login')} />
  if (mode === 'join') return <Join onIn={onIn} onBack={() => setMode('login')} />
  return <SignIn onIn={onIn} go={setMode} />
}

function useSubmit(fn) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const run = async (e) => {
    e?.preventDefault()
    setBusy(true); setErr(null)
    try { await fn() } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  return [run, busy, err]
}

function SignIn({ onIn, go }) {
  const [f, setF] = useState({ login_id: '', password: '' })
  const [submit, busy, err] = useSubmit(async () => onIn(await api('/auth/login', { method: 'POST', body: f })))
  return (
    <form className="app" onSubmit={submit}>
      <Title title="쿠션톡" side="학부모 · 선생님 · 관리자" />
      <div className="page">
        <div className="cxr"><Cushi face="hi" label="인사하는 쿠션이" /><div className="say">어서 오세요! 아이디로 들어와 주세요.</div></div>
        <label className="lbl" htmlFor="lid">아이디</label>
        <input id="lid" className="field" autoComplete="username" value={f.login_id} onChange={(e) => setF({ ...f, login_id: e.target.value })} />
        <label className="lbl" htmlFor="pw">비밀번호</label>
        <input id="pw" className="field" type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        {err && <p className="err" role="alert">{err.message}</p>}
        <Btn disabled={busy || !f.login_id || !f.password}>로그인</Btn>
        <Btn kind="white" type="button" onClick={() => go('signup')}>처음이에요 · 학부모 가입</Btn>
        <button type="button" className="btn b-ghost" onClick={() => go('join')}>학생이에요 · 참여 코드로 들어가기</button>
        <p className="cap center">학생은 로그인 없이 선생님이 알려 준 참여 코드로 들어와요.</p>
      </div>
    </form>
  )
}

function Signup({ onIn, onBack }) {
  const [q, setQ] = useState('')
  const [found, setFound] = useState([])
  const [school, setSchool] = useState(null)
  const [f, setF] = useState({ name: '', login_id: '', password: '' })
  const search = async (v) => {
    setQ(v); setSchool(null)
    setFound(v.trim().length >= 2 ? (await api(`/schools?q=${encodeURIComponent(v.trim())}`).catch(() => ({ schools: [] }))).schools : [])
  }
  const [submit, busy, err] = useSubmit(async () => onIn(await api('/auth/signup', { method: 'POST', body: { ...f, school_id: school.id } })))
  return (
    <form className="app" onSubmit={submit}>
      <Header title="학부모 가입" sub="아이 학교부터 골라 주세요" onBack={onBack} />
      <div className="page tight">
        <label className="lbl" htmlFor="sq">학교 이름 검색</label>
        <input id="sq" className="field" value={q} placeholder="두 글자 이상" onChange={(e) => search(e.target.value)} />
        {found.map((s) => (
          <button type="button" key={s.id} className="chunk row" style={school?.id === s.id ? { borderColor: 'var(--ink)' } : null} onClick={() => setSchool(s)}>
            <b className="grow">{s.name}</b>{school?.id === s.id && <b>✓</b>}
          </button>
        ))}
        <label className="lbl" htmlFor="nm">이름</label>
        <input id="nm" className="field" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <label className="lbl" htmlFor="nid">아이디 (영문 · 숫자 3자 이상)</label>
        <input id="nid" className="field" autoComplete="username" value={f.login_id} onChange={(e) => setF({ ...f, login_id: e.target.value })} />
        <label className="lbl" htmlFor="npw">비밀번호 (8자 이상)</label>
        <input id="npw" className="field" type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        {err && <p className="err" role="alert">{err.message}</p>}
        <Btn disabled={busy || !school || !f.name || f.login_id.length < 3 || f.password.length < 8}>가입하기</Btn>
      </div>
    </form>
  )
}

function Join({ onIn, onBack }) {
  const [f, setF] = useState({ code: '', name: '' })
  const [submit, busy, err] = useSubmit(async () => onIn(await api('/rooms/join', { method: 'POST', body: f })))
  return (
    <form className="app" onSubmit={submit}>
      <Header title="반 톡방 참여" onBack={onBack} />
      <div className="page tight">
        {!err && <div className="cxr"><Cushi face="hi" label="인사하는 쿠션이" /><div className="say">반가워요! 선생님이 알려 준 코드를 넣어 주세요.</div></div>}
        <label className="lbl" htmlFor="code">참여 코드</label>
        <input id="code" className={`field jua${err ? ' bad' : ''}`} style={{ fontSize: 20, letterSpacing: '.1em' }} value={f.code} maxLength={8}
          onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
        {err && <p className="err" role="alert">{err.message}</p>}
        <label className="lbl" htmlFor="sname">이름</label>
        <input id="sname" className="field" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <Btn disabled={busy || f.code.replace(/\s/g, '').length < 6 || !f.name.trim()}>참여하기</Btn>
        <p className="cap center">학교 계정 없이 참여 코드와 이름만 넣으면 돼요.</p>
      </div>
    </form>
  )
}
