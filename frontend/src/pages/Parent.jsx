// A0 선생님 목록 · A1~A5 학부모 작성 · 경고 시트
import { useState } from 'react'
import { api, usePoll, useUnread, TYPES, when } from '../api.js'
import { Btn, Composer, Cushi, Dot, Header, Ic, Marked, Sheet, TabBar, Title } from '../components/ui.jsx'
import { Apply, AttendanceForm, Feed, FieldTripForm, Home } from './School.jsx'
import { CounselBook, useMyCounsel } from './Care.jsx'
import { AccountSheet, MenuCtx, SectionHead } from './TeacherHome.jsx'

// 하단바 = 큰 구역(홈 · 연락 · 신청 · 소식). 내 정보는 상단 사람 아이콘 (교사와 같은 규칙)
export default function Parent({ me, onOut }) {
  const [tab, setTab] = useState('홈')
  const [sub, setSub] = useState(null) // att · trip · 대화 중인 반
  const [feedFirst, setFeedFirst] = useState('all')
  const [menu, setMenu] = useState(false)
  const [mine, setMine] = useState([])
  const [sig, setSig] = useState({})
  const [news, setNews] = useState({ nb: 0, fresh: 0 }) // 소식 칸 숫자: 안 읽은 알림장 + 마지막 방문 뒤 올라온 공지
  const [unread] = useUnread()
  const seenKey = `cushion_seen_news_${me.id}`
  const seen = () => { try { return Number(localStorage.getItem(seenKey)) || 0 } catch { return 0 } }
  const markSeen = () => { try { localStorage.setItem(seenKey, String(Date.now())) } catch { /* 저장 못 하면 숫자가 계속 남을 뿐 */ } setNews((n) => ({ ...n, fresh: 0 })) }
  usePoll(async () => setMine((await api('/parent/teachers')).mine), [])
  const home = mine[0] // ponytail: 홈은 첫 담임 기준. 담임이 여럿인 학부모가 많아지면 반 고르기
  usePoll(async () => { if (home) setSig(await api(`/classes/${home.class_id}/today`)) }, [home?.class_id])
  const cs = useMyCounsel(home?.class_id)
  usePoll(async () => {
    if (!home) return
    const [nb, nt] = await Promise.all([api(`/classes/${home.class_id}/notebooks`), api(`/classes/${home.class_id}/notices`)])
    setNews({ nb: nb.items.filter((i) => !i.mine).length, fresh: tab === '소식' ? 0 : nt.items.filter((n) => Date.parse(n.created_at) > seen()).length })
  }, [home?.class_id, tab])
  const back = () => setSub(null)
  if (sub?.class_id) return <Conversation cls={sub} onBack={back} />
  if (sub === 'att') return <AttendanceForm cls={home} onBack={back} />
  if (sub === 'trip') return <FieldTripForm cls={home} onBack={back} />
  if (sub === 'counsel') return <CounselBook cls={home} onBack={back} />
  const go = (to) => {
    if (to === 'att' || to === 'trip' || to === 'counsel') return setSub(to)
    if (to === 'survey') { setFeedFirst('survey'); return setTab('소식') }
    if (to === '소식') { setFeedFirst(news.nb > 0 ? 'notebook' : 'all'); markSeen(); return setTab('소식') }
    setFeedFirst('all'); setTab(to)
  }
  return (
    <MenuCtx.Provider value={() => setMenu(true)}>
      {tab === '홈' && <Home me={me} cls={home} go={go} unread={unread} />}
      {tab === '연락' && <Teachers me={me} onOpen={setSub} />}
      {tab === '신청' && <Apply cls={home} go={go} />}
      {tab === '소식' && (home ? <Feed key={feedFirst} classId={home.class_id} first={feedFirst} /> : <div className="app"><SectionHead title="학교소식" /><div className="page"><Btn onClick={() => go('연락')}>선생님 고르기</Btn></div></div>)}
      <TabBar tabs={['홈', '연락', '신청', '소식']} on={tab} onPick={(t) => { if (t === '소식') { setFeedFirst(news.nb > 0 ? 'notebook' : 'all'); markSeen() } else setFeedFirst('all'); setTab(t) }}
        badges={{ 연락: unread, 신청: (sig.open_surveys || 0) + (cs?.open && !cs.mine ? 1 : 0), 소식: news.nb + news.fresh }} />
      {menu && <AccountSheet me={me} sub={home ? `${home.child_name} · ${home.grade}학년 ${home.class_no}반` : me.school_name} onClose={() => setMenu(false)} onOut={onOut} />}
    </MenuCtx.Provider>
  )
}

function Teachers({ me, onOpen }) {
  const [data, setData] = useState({ mine: [], others: [] })
  const [pick, setPick] = useState(null)
  const [child, setChild] = useState('')
  const [err, setErr] = useState(null)
  const [unread, clearUnread] = useUnread()
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
      <SectionHead title="연락" />
      <div className="page tight">
        {data.mine.length > 0 && <p className="sec">내 아이 담임{unread > 0 && <> · 새 답장<Dot n={unread} /></>}</p>}
        {/* ponytail: 알림에 반 번호가 없어 대화를 열면 모두 읽음. 담임이 여럿인 학부모가 많아지면 반별로 */}
        {data.mine.map((c) => <Row key={c.class_id} c={c} onClick={() => { clearUnread(); onOpen(c) }} />)}
        <p className="sec">다른 반</p>
        {data.others.map((c) => <Row key={c.class_id} c={c} onClick={() => { setPick(c); setChild(''); setErr(null) }} />)}
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
  const [type, setType] = useState('other') // 유형을 안 골라도 보낼 수 있게 기본은 기타
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
      await api('/parent/messages', { method: 'POST', body: { class_id: cls.class_id, text: body, msg_type: type, used_suggestion: used } })
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
      <Header onBack={onBack} title={`${cls.grade}학년 ${cls.class_no}반 담임 선생님`} />
      <div className="page tight">
        {items?.map((m) => m.kind === 'reply'
          ? <div key={`r${m.id}`} className="bub">{m.text}<div className="cap">{when(m.at)}</div></div>
          : <div key={`m${m.id}`} style={{ display: 'contents' }}>
              <div className="bub me">{m.text}</div>
              {m.done && <span className="rxpill chk me" title="선생님이 확인했어요"><Ic name="tick" size={12} /></span>}
              <div className="meta">{m.used_suggestion && <span className="tag tg-line">제안 문장으로 보냄</span>}<span>{TYPES[m.msg_type]} · {when(m.at)}</span></div>
            </div>)}
      </div>
      <Composer placeholder="메시지" value={text} onChange={setText} onSend={check} busy={!!stage}>
        {stage === 'checking' && <div className="row cap"><Cushi face="read" size={30} />확인 중</div>}
        {editing && <><div className="quote"><Marked text={editing.text} spans={editing.spans} /></div></>}
        {err && <p className="err" role="alert">{err}</p>}
        <div className="picks">
          <select className="sel" value={type} onChange={(e) => setType(e.target.value)} aria-label="요청 유형">
            <option value="">유형 고르기</option>
            {Object.entries(TYPES).filter(([k]) => k !== 'absence').map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
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
            <div className="tags">{warn.keeps.map((k) => <span key={k} className="tag tg-mint">✓ {k}</span>)}</div>
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
