// 시작 화면 → 학부모 · 선생님/교직원: 소셜 로그인 → (처음이면) 학교 확인 → 승인 대기 / 학생: 참여 코드
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Btn, Cushi, Header, Sheet, Title } from '../components/ui.jsx'

const PROVIDERS = [['kakao', '카카오'], ['google', '구글']]

const Svg = ({ children }) => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
)
// 학부모: 어른 + 아이
const ParentIcon = () => (
  <Svg><circle cx="9" cy="7" r="3.2" /><path d="M3 20v-2.5A4.5 4.5 0 0 1 7.5 13h3A4.5 4.5 0 0 1 15 17.5V20" /><circle cx="17.5" cy="11.5" r="2.2" /><path d="M16.5 20v-1.8a3 3 0 0 1 3-3H21" /></Svg>
)
// 선생님: 칠판
const TeacherIcon = () => (
  <Svg><rect x="3" y="4" width="18" height="12" rx="1.5" /><path d="M7 9h6M7 12h4" /><path d="M8 20l2-4M16 20l-2-4" /></Svg>
)
// 학생: 학사모
const StudentIcon = () => (
  <Svg><path d="M2 9l10-5 10 5-10 5z" /><path d="M6 11.2V16c0 1.4 2.7 3 6 3s6-1.6 6-3v-4.8" /><path d="M22 9v6" /></Svg>
)

// 소셜 로그인에서 돌아왔을 때 주소의 #login=... 을 읽는다 (읽은 뒤 주소는 지움)
function readCallback() {
  const m = location.hash.match(/^#login=(.+)$/)
  if (!m) return null
  history.replaceState(null, '', location.pathname)
  try { return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(m[1].replace(/-/g, '+').replace(/_/g, '/')), (ch) => ch.charCodeAt(0)))) } catch { return null }
}

export default function Login({ onIn }) {
  const [cb] = useState(readCallback)
  const [view, setView] = useState(!cb ? 'start' : cb.kind === 'pending' ? 'pending' : cb.role === 'staff' ? 'staff' : 'parent') // start · parent · staff · student · test · pending
  useEffect(() => { if (cb?.kind === 'in') onIn(cb) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const [cfg, setCfg] = useState({ demo_login: false })
  useEffect(() => { api('/config').then(setCfg).catch(() => {}) }, [])
  const back = () => setView('start')
  if (view === 'student') return <Join onIn={onIn} onBack={back} />
  if (view === 'test') return <TestLogin onIn={onIn} onBack={back} />
  if (view === 'pending') return <Pending onBack={back} />
  if (view === 'parent' || view === 'staff') return <Social role={view} cfg={cfg} init={cb} onIn={onIn} onBack={back} onPending={() => setView('pending')} />
  return (
    <div className="app">
      <Title title="쿠션톡" />
      <div className="page">
        <div className="cxr" style={{ alignItems: 'flex-end' }}>
          <Cushi face="hi" size={92} label="인사하는 쿠션이" />
          
        </div>
        <div style={{ height: 8 }} />
        <div className="tiles">
          <button className="tile parent wide" onClick={() => setView('parent')}><span className="ic"><ParentIcon /></span>학부모</button>
          <button className="tile staff" onClick={() => setView('staff')}><span className="ic"><TeacherIcon /></span>선생님 · 교직원</button>
          <button className="tile student" onClick={() => setView('student')}><span className="ic"><StudentIcon /></span>학생</button>
        </div>
        {cfg.demo_login && <button className="cap center" style={{ textDecoration: 'underline' }} onClick={() => setView('test')}>개발용 테스트 계정으로 들어가기</button>}
      </div>
    </div>
  )
}

// 제공자 로고 (공식 색)
const KakaoLogo = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#191919" d="M12 3C6.5 3 2 6.6 2 11c0 2.8 1.8 5.3 4.6 6.7l-1 3.6c-.1.3.3.6.6.4l4.2-2.8c.5.1 1 .1 1.6.1 5.5 0 10-3.6 10-8S17.5 3 12 3z" /></svg>
const IdLogo = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" /></svg>
const GoogleLogo = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.7v3h3.9c2.3-2.1 3.5-5.2 3.5-8.9z" /><path fill="#34A853" d="M12 24c3.2 0 6-1.1 7.9-2.9l-3.9-3c-1.1.7-2.4 1.1-4 1.1-3.1 0-5.7-2.1-6.6-4.9H1.4v3.1A12 12 0 0 0 12 24z" /><path fill="#FBBC05" d="M5.4 14.3a7.2 7.2 0 0 1 0-4.6V6.6H1.4a12 12 0 0 0 0 10.8z" /><path fill="#EA4335" d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.4 6.6l4 3.1C6.3 6.9 8.9 4.8 12 4.8z" /></svg>
)

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

function Social({ role, cfg, init, onIn, onBack, onPending }) {
  const [ask, setAsk] = useState(null) // 데모 로그인 시트를 연 제공자
  const [demoName, setDemoName] = useState('')
  const [join, setJoin] = useState(init?.kind === 'signup' ? init : null) // 처음 온 사람: { ticket, name, provider }
  const [msg, setMsg] = useState(init?.kind === 'error' ? init.message : null)
  const [idMode, setIdMode] = useState(false) // 일반 가입 · 로그인
  const staff = role === 'staff'

  const finish = (r) => (r.pending ? onPending() : onIn(r))
  const tryProvider = async (provider, token) => {
    setMsg(null)
    try {
      const r = await api('/auth/social', { method: 'POST', body: { provider, token } })
      if (r.needs_signup) { setAsk(null); setJoin({ ...r, provider }) } else onIn(r)
    } catch (e) { e.code === 'PENDING_APPROVAL' ? onPending() : setMsg(e.message) }
  }
  const pick = (provider) => {
    if (cfg.ready?.includes(provider)) location.href = `/api/auth/${provider}/start?role=${role}` // 진짜 로그인 창으로
    else if (cfg.demo_login) { setDemoName(''); setAsk(provider) } // 개발자 앱 키가 오기 전까지는 이름만 넣는 데모
    else setMsg('아직 연결 전이에요')
  }

  if (idMode) return <IdAuth staff={staff} onIn={onIn} onBack={() => setIdMode(false)} onPending={onPending} />
  if (join) return <SchoolStep staff={staff} join={join} onDone={finish} onBack={() => setJoin(null)} />
  return (
    <div className="app">
      <Header title={staff ? '선생님 · 교직원으로 시작하기' : '학부모로 시작하기'} onBack={onBack} />
      <div className="page tight" style={{ paddingTop: 24 }}>
        <button className="soc kakao" onClick={() => pick('kakao')}><KakaoLogo />카카오로 시작하기</button>
        <button className="soc google" onClick={() => pick('google')}><GoogleLogo />구글로 시작하기</button>
        <button className="soc plain" onClick={() => setIdMode(true)}><IdLogo />아이디로 시작하기</button>
        {msg && <p className="err" role="alert">{msg}</p>}
      </div>
      {ask && (
        <Sheet onClose={() => setAsk(null)}>
          <h3>{PROVIDERS.find((p) => p[0] === ask)[1]} 데모 로그인</h3>
          <label className="lbl" htmlFor="dn">이름</label>
          <input id="dn" className="field" value={demoName} autoFocus onChange={(e) => setDemoName(e.target.value)} />
          <Btn disabled={!demoName.trim()} onClick={() => tryProvider(ask, `demo:${demoName.trim()}`)}>시작하기</Btn>
        </Sheet>
      )}
    </div>
  )
}

// 일반 가입 · 로그인 (아이디 + 비밀번호). 가입은 아이디 · 비밀번호 → 학교 확인 순서
function IdAuth({ staff, onIn, onBack, onPending }) {
  const [mode, setMode] = useState('login') // login · signup
  const [f, setF] = useState({ login_id: '', password: '' })
  const [step, setStep] = useState(null) // 가입: 아이디 · 비밀번호를 받은 뒤 학교 확인으로
  const [submit, busy, err] = useSubmit(async () => {
    try { onIn(await api('/auth/login', { method: 'POST', body: f })) } catch (e) { if (e.code === 'PENDING_APPROVAL') onPending(); else throw e }
  })
  if (step) return <SchoolStep staff={staff} join={{ credentials: f, name: '' }} onDone={(r) => (r.pending ? onPending() : onIn(r))} onBack={() => setStep(null)} />
  const signup = mode === 'signup'
  const okId = /^[A-Za-z0-9_]{4,20}$/.test(f.login_id)
  return (
    <form className="app" onSubmit={signup ? (e) => { e.preventDefault(); setStep(true) } : submit}>
      <Header title={signup ? '아이디로 가입하기' : '아이디로 로그인'} onBack={onBack} />
      <div className="page tight">
        <div className="seg" style={{ marginBottom: 4 }}>
          <button type="button" className={!signup ? 'on' : ''} onClick={() => setMode('login')}>로그인</button>
          <button type="button" className={signup ? 'on' : ''} onClick={() => setMode('signup')}>가입</button>
        </div>
        <label className="lbl" htmlFor="iid">아이디</label>
        <input id="iid" className="field" autoComplete="username" value={f.login_id} onChange={(e) => setF({ ...f, login_id: e.target.value })} />
        <label className="lbl" htmlFor="ipw">비밀번호</label>
        <input id="ipw" className="field" type="password" autoComplete={signup ? 'new-password' : 'current-password'} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        {err && <p className="err" role="alert">{err.message}</p>}
        <Btn disabled={busy || !f.login_id || !f.password || (signup && (!okId || f.password.length < 8))}>{signup ? '다음' : '로그인'}</Btn>
      </div>
    </form>
  )
}

function SchoolStep({ staff, join, onDone, onBack }) {
  const [q, setQ] = useState('')
  const [found, setFound] = useState([])
  const [school, setSchool] = useState(null)
  const [name, setName] = useState(join.name)
  const [role, setRole] = useState(staff ? 'teacher' : 'parent')
  const search = async (v) => {
    setQ(v); setSchool(null)
    setFound(v.trim().length >= 2 ? (await api(`/schools?q=${encodeURIComponent(v.trim())}`).catch(() => ({ schools: [] }))).schools : [])
  }
  const [submit, busy, err] = useSubmit(async () => onDone(await api(join.credentials ? '/auth/signup' : '/auth/social/signup', {
    method: 'POST', body: { ...(join.credentials || { ticket: join.ticket }), role, school_id: school.id, name: name.trim() } })))
  return (
    <form className="app" onSubmit={submit}>
      <Header title="학교 확인" onBack={onBack} />
      <div className="page tight">
        <label className="lbl" htmlFor="sq">학교 이름</label>
        <input id="sq" className="field" value={q} onChange={(e) => search(e.target.value)} />
        {found.map((s) => (
          <button type="button" key={s.id} className={`choice${school?.id === s.id ? ' on' : ''}`} onClick={() => setSchool(s)}>
            <b className="grow">{s.name}</b>{school?.id === s.id && <b>✓</b>}
          </button>
        ))}
        <label className="lbl" htmlFor="nm">이름</label>
        <input id="nm" className="field" value={name} onChange={(e) => setName(e.target.value)} />
        {staff && <>
          <p className="lbl">역할</p>
          {[['teacher', '담임 선생님'], ['admin', '교감 · 민원대응팀']].map(([k, label]) => (
            <button type="button" key={k} role="radio" aria-checked={role === k} className={`choice${role === k ? ' on' : ''}`} onClick={() => setRole(k)}><span className="radio" />{label}</button>
          ))}
        </>}
        {err && <p className="err" role="alert">{err.message}</p>}
        <Btn disabled={busy || !school || !name.trim()}>{staff ? '승인 요청하기' : '시작하기'}</Btn>
      </div>
    </form>
  )
}

function Pending({ onBack }) {
  return (
    <div className="app">
      <Header title="승인 대기" onBack={onBack} />
      <div className="page">
        <div className="empty">
          <Cushi face="rest" size={96} label="쉬는 중인 쿠션이" />
          <b>승인을 기다리고 있어요</b>
        </div>
        <Btn kind="white" onClick={onBack}>처음으로</Btn>
      </div>
    </div>
  )
}

function Join({ onIn, onBack }) {
  const [f, setF] = useState({ code: '', name: '' })
  const [submit, busy, err] = useSubmit(async () => onIn(await api('/rooms/join', { method: 'POST', body: f })))
  return (
    <form className="app" onSubmit={submit}>
      <Header title="학생으로 시작하기" onBack={onBack} />
      <div className="page tight">
        <label className="lbl" htmlFor="code">참여 코드</label>
        <input id="code" className={`field jua${err ? ' bad' : ''}`} style={{ fontSize: 22, letterSpacing: '.12em' }} value={f.code} maxLength={8}
          onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
        {err && <p className="err" role="alert">{err.message}</p>}
        <label className="lbl" htmlFor="sname">이름</label>
        <input id="sname" className="field" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <Btn disabled={busy || f.code.replace(/\s/g, '').length < 6 || !f.name.trim()}>참여하기</Btn>
      </div>
    </form>
  )
}

// 개발 · 시연용: 시드 계정(비밀번호 pass1234)으로 바로 들어간다
function TestLogin({ onIn, onBack }) {
  const [f, setF] = useState({ login_id: '', password: 'pass1234' })
  const [submit, busy, err] = useSubmit(async () => onIn(await api('/auth/login', { method: 'POST', body: f })))
  return (
    <form className="app" onSubmit={submit}>
      <Header title="테스트 계정" sub="개발용 · teacher1 · parent1 · admin1 · student1" onBack={onBack} />
      <div className="page tight">
        <label className="lbl" htmlFor="lid">아이디</label>
        <input id="lid" className="field" autoComplete="username" value={f.login_id} onChange={(e) => setF({ ...f, login_id: e.target.value })} />
        <label className="lbl" htmlFor="pw">비밀번호</label>
        <input id="pw" className="field" type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        {err && <p className="err" role="alert">{err.message}</p>}
        <Btn disabled={busy || !f.login_id || !f.password}>들어가기</Btn>
      </div>
    </form>
  )
}
