// 시작 화면 → 학부모 · 선생님/교직원: 소셜 로그인 → (처음이면) 학교 확인 → 승인 대기 / 학생: 참여 코드
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Btn, Cushi, Header, Sheet, Title } from '../components/ui.jsx'

const PROVIDERS = [['kakao', '카카오'], ['naver', '네이버'], ['google', '구글']]

export default function Login({ onIn }) {
  const [view, setView] = useState('start') // start · parent · staff · student · test · pending
  const [cfg, setCfg] = useState({ demo_login: false })
  useEffect(() => { api('/config').then(setCfg).catch(() => {}) }, [])
  const back = () => setView('start')
  if (view === 'student') return <Join onIn={onIn} onBack={back} />
  if (view === 'test') return <TestLogin onIn={onIn} onBack={back} />
  if (view === 'pending') return <Pending onBack={back} />
  if (view === 'parent' || view === 'staff') return <Social role={view} cfg={cfg} onIn={onIn} onBack={back} onPending={() => setView('pending')} />
  return (
    <div className="app">
      <Title title="쿠션톡" side="학교 공식 창구" />
      <div className="page">
        <div className="cxr" style={{ alignItems: 'flex-end' }}>
          <Cushi face="hi" size={92} label="인사하는 쿠션이" />
          <div className="say" style={{ fontSize: 17, lineHeight: 1.4, marginBottom: 8 }}>안녕하세요,<br />누구로 시작할까요?</div>
        </div>
        <div style={{ height: 8 }} />
        <button className="role main" onClick={() => setView('parent')}>
          <span className="ic" style={{ background: 'var(--sky)', color: '#fff' }}>부</span>
          <span>학부모<small>선생님께 연락해요</small></span>
        </button>
        <button className="role" onClick={() => setView('staff')}>
          <span className="ic" style={{ background: 'var(--butter-soft)', color: '#A9861F' }}>선</span>
          <span>선생님 · 교직원<small>메시지를 확인하고 답장해요</small></span>
        </button>
        <button className="role" onClick={() => setView('student')}>
          <span className="ic" style={{ background: 'var(--mint-soft)', color: '#23876A' }}>학</span>
          <span>학생<small>선생님께 받은 코드로 들어가요</small></span>
        </button>
        <p className="cap center" style={{ marginTop: 18 }}>학부모 메시지는 쿠션이가 먼저 읽어요</p>
        {cfg.demo_login && <button className="cap center" style={{ textDecoration: 'underline' }} onClick={() => setView('test')}>개발용 테스트 계정으로 들어가기</button>}
      </div>
    </div>
  )
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

function Social({ role, cfg, onIn, onBack, onPending }) {
  const [ask, setAsk] = useState(null) // 데모 로그인 시트를 연 제공자
  const [demoName, setDemoName] = useState('')
  const [join, setJoin] = useState(null) // 처음 온 사람: { ticket, name }
  const [msg, setMsg] = useState(null)
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
    if (cfg.demo_login) { setDemoName(''); setAsk(provider) } // 개발자 앱 키가 오기 전까지는 이름만 넣는 데모
    else setMsg('이 로그인은 아직 연결 전이에요. 학교 관리자에게 문의해 주세요.')
  }

  if (join) return <SchoolStep staff={staff} join={join} onDone={finish} onBack={() => setJoin(null)} />
  return (
    <div className="app">
      <Header title={staff ? '선생님 · 교직원으로 시작하기' : '학부모로 시작하기'} onBack={onBack} />
      <div className="page tight" style={{ paddingTop: 24 }}>
        <button className="soc kakao" onClick={() => pick('kakao')}><span className="bubble" />카카오로 시작하기</button>
        <button className="soc naver" onClick={() => pick('naver')}><span className="g">N</span>네이버로 시작하기</button>
        <button className="soc google" onClick={() => pick('google')}><span className="g" style={{ color: '#4285F4' }}>G</span>구글로 시작하기</button>
        {msg && <p className="err" role="alert">{msg}</p>}
        <p className="cap" style={{ lineHeight: 1.55, marginTop: 6 }}>
          처음이면 가입, 이미 계정이 있으면 바로 로그인돼요.{staff && ' 선생님 · 교직원은 학교 관리자가 확인한 뒤부터 쓸 수 있어요.'}
        </p>
      </div>
      {ask && (
        <Sheet onClose={() => setAsk(null)}>
          <h3>{PROVIDERS.find((p) => p[0] === ask)[1]} 데모 로그인</h3>
          <p className="cap center">개발용이에요. 개발자 앱 키가 연결되면 진짜 로그인 창이 떠요.</p>
          <label className="lbl" htmlFor="dn">이름</label>
          <input id="dn" className="field" value={demoName} autoFocus onChange={(e) => setDemoName(e.target.value)} />
          <Btn disabled={!demoName.trim()} onClick={() => tryProvider(ask, `demo:${demoName.trim()}`)}>시작하기</Btn>
        </Sheet>
      )}
    </div>
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
  const [submit, busy, err] = useSubmit(async () => onDone(await api('/auth/social/signup', { method: 'POST', body: { ticket: join.ticket, role, school_id: school.id, name: name.trim() } })))
  return (
    <form className="app" onSubmit={submit}>
      <Header title="학교 확인" onBack={onBack} />
      <div className="page tight">
        <p style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-.8px', lineHeight: 1.3, padding: '4px 2px 6px' }}>처음 오셨네요.<br />{staff ? '학교를 알려 주세요' : '아이 학교를 알려 주세요'}</p>
        <label className="lbl" htmlFor="sq">학교 이름</label>
        <input id="sq" className="field" value={q} placeholder="두 글자 이상" onChange={(e) => search(e.target.value)} />
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
          <p className="note">학교 관리자가 확인한 뒤부터 쓸 수 있어요. 보통 하루 안에 끝나요.</p>
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
          <p className="cap">학교 관리자가 확인하면 같은 방법으로 로그인할 수 있어요. 승인되기 전에는 들어올 수 없어요.</p>
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
        <p style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-.8px', lineHeight: 1.3, padding: '4px 2px 6px' }}>선생님이 알려 준<br />코드를 넣어 주세요</p>
        <label className="lbl" htmlFor="code">참여 코드</label>
        <input id="code" className={`field jua${err ? ' bad' : ''}`} style={{ fontSize: 22, letterSpacing: '.12em' }} value={f.code} maxLength={8}
          onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
        {err && <p className="err" role="alert">{err.message}</p>}
        <label className="lbl" htmlFor="sname">이름</label>
        <input id="sname" className="field" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <Btn disabled={busy || f.code.replace(/\s/g, '').length < 6 || !f.name.trim()}>참여하기</Btn>
        <p className="cap" style={{ lineHeight: 1.55 }}>코드는 선생님만 만들 수 있어요. 학생은 따로 가입하지 않아요.</p>
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
      <Header title="테스트 계정" sub="개발용 · teacher1 · parent1 · admin1" onBack={onBack} />
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
