// 교사 화면: 하단바 = 큰 구역(메시지 · 출결 · 승인 · 보내기 · 설정), 위쪽 탭 = 그 구역 안의 갈래
// 긴급이 있으면 하단 메시지 칸이 빨갛게, 출결 · 승인 · 메시지는 칸 위 빨간 원 숫자
import { createContext, useContext, useEffect, useState } from 'react'
import { api, usePoll, ATT_KIND, CASE, TYPES, URGENT, dday, when, dateText } from '../api.js'
import { Btn, Chip, ClassHead, Cushi, Ic, Loading, Sheet } from '../components/ui.jsx'

const TRIP = { pending: ['coral', '대기'], approved: ['mint', '승인'], rejected: ['slate', '반려'] }

// 필요한 것을 한 번에 가져와 10초마다 새로 고침
export function useTeacherHome(classId) {
  const [d, setD] = useState(null)
  const load = async () => {
    const [todo, school, att, trips, nb, cs] = await Promise.all([
      api('/teacher/inbox?filter=todo'), api('/teacher/inbox?filter=school'), api('/teacher/attendance'), api('/teacher/field-trips'),
      classId ? api(`/classes/${classId}/notebooks`) : null, classId ? api(`/classes/${classId}/counsel`) : null])
    setD({ todo, school, att, trips: trips.items, notebooks: nb?.items ?? null, counsel: cs?.items ?? [] })
  }
  usePoll(load, [classId])
  return [d, load]
}

// 하단바 숫자와 빨간 칸 (Teacher.jsx가 씀)
export function tabSignals(d, off = false) {
  if (!d) return { badges: {}, alerts: {} }
  return {
    badges: off ? { 메시지: d.todo.urgent.length } : { 메시지: d.todo.urgent.length + d.todo.items.length, 출결: d.att.pending, 승인: d.trips.filter((t) => t.status === 'pending').length },
    alerts: { 메시지: d.todo.urgent.length > 0 },
  }
}

// 구역 머리글: 로고 대신 구역 이름. 아래 본문과 이어지도록 위에서 아래로 옅어지는 바탕
export const MenuCtx = createContext(null)
export const AlarmCtx = createContext(false) // 알림이 꺼진 동안: 머리글은 회색, 쿠션이는 잠든 얼굴
// 구역 머리글: 제목 앞에 작은 쿠션이 (관리자 화면은 mascot={false}: 위협을 다루는 화면에는 쿠션이가 없다)
export function SectionHead({ title, side, children, mascot = true, extra, quiet }) {
  const openMenu = useContext(MenuCtx)
  const asleep = useContext(AlarmCtx) || !!quiet
  return (
    <div className={`shead${asleep ? ' quiet' : ''}`}>
      <div className="topbar"><span className="brand">{mascot && <Cushi face={asleep ? 'rest' : 'hi'} size={28} label="" />}<b>{title}</b></span>
        <span className="r">{extra}{side && <span className="d">{side}</span>}
          {openMenu && <button className="menu" onClick={openMenu} aria-label="내 계정"><Ic name="내 정보" size={22} /></button>}</span></div>
      {children}
    </div>
  )
}

// 상단 사람 아이콘 → 프로필 · 참여 코드 · 로그아웃
export function AccountSheet({ me, room, sub, onClose, onCode, onOut }) {
  return (
    <Sheet onClose={onClose}>
      <div className="chead" style={{ padding: '4px 0 8px' }}>
        <span className="badge">{me.name?.[0]}</span>
        <div className="g"><b>{me.name}{{ teacher: ' 선생님', parent: ' 보호자님', student: ' 학생', admin: ' 관리자' }[me.role] || ''}</b><small>{sub ?? `${me.school_name}${room ? ` · ${room.grade}학년 ${room.class_no}반` : ''}`}</small></div>
      </div>
      <div className="ls" style={{ margin: '0 -20px' }}>
        {room && <button className="li" style={{ padding: '14px 20px' }} onClick={onCode}><div className="g"><b>반 톡방 참여 코드</b></div><span className="go">›</span></button>}
        <button className="li" style={{ padding: '14px 20px', color: 'var(--coral-deep)' }} onClick={onOut}><div className="g"><b>로그아웃</b></div></button>
      </div>
    </Sheet>
  )
}

function MsgRow({ m, onClick, onDone, checking }) {
  const done = m.analysis_status === 'done'
  const Wrap = onDone ? 'div' : 'button'
  return (
    <Wrap className="li" onClick={onDone ? undefined : onClick}>
      {onDone && <button className={`cb${checking ? ' on' : ''}`} onClick={() => onDone(m.id)} role="checkbox" aria-checked={!!checking} aria-label="확인">{checking && <Ic name="tick" size={14} />}</button>}
      <div className="g" onClick={onDone ? onClick : undefined} style={onDone ? { cursor: 'pointer' } : undefined}>
        <div className="rowc"><b>{m.child_name} 보호자</b>{done && <Chip kind="sky">{TYPES[m.msg_type]}</Chip>}
          {m.category === 'threat' && <Chip kind="slate">{CASE[m.case_status]}</Chip>}<span className="t">{when(m.received_at)}</span></div>
        <p>{done ? m.summary : m.analysis_status === 'failed' ? '분석 실패' : '분석 중'}
          {done && m.masked_count > 0 && <Chip kind="butter">{m.masked_count}곳 막음</Chip>}</p>
      </div>
      <span className="go" onClick={onDone ? onClick : undefined}>›</span>
    </Wrap>
  )
}

const Empty = ({ title }) => (
  <div className="empty"><span className="ring"><Ic name="check" size={32} /></span><b>{title}</b></div>
)

// ───────── 메시지 (홈): 반 머리글 + 위 탭 [답장할 것 · 학교가 맡은 일] ─────────
// 알림 끄기: 끄면 일반 연락(답장할 것)이 화면에서 사라지고 긴급 · 안전만 남는다. 시간이 지나면 저절로 켜진다.
export function useAlarm() {
  const [until, setUntil] = useState(null)
  const [tick, setTick] = useState(0)
  useEffect(() => { api('/teacher/alarm').then((r) => setUntil(r.off_until)).catch(() => {}) }, [])
  useEffect(() => { const t = setInterval(() => setTick((n) => n + 1), 20000); return () => clearInterval(t) }, [])
  void tick // 20초마다 다시 그려서 끌 시간이 지났는지 본다
  const off = !!until && Date.parse(until) > Date.now()
  const set = async (iso) => setUntil((await api('/teacher/alarm', { method: 'POST', body: { until: iso } })).off_until)
  return { off, until, set }
}

function AlarmSwitch({ alarm, onAsk }) {
  return (
    <span className="alarm">
      <small>{alarm.off ? `${new Date(alarm.until).toTimeString().slice(0, 5)}까지` : '알림'}</small>
      <button className={`sw${alarm.off ? ' off' : ''}`} role="switch" aria-checked={!alarm.off} aria-label="알림" onClick={() => (alarm.off ? alarm.set(null) : onAsk())} />
    </span>
  )
}

// 몇 시까지 끌지: 슬라이더를 움직이면 끝나는 시각이 바로 크게 보인다. 끄기는 시트 맨 아래에 꽉 찬 바.
const STEP = 10 // 분
const clockAfter = (mins) => { const t = new Date(Date.now() + mins * 60000); t.setSeconds(0, 0); t.setMinutes(Math.ceil(t.getMinutes() / STEP) * STEP); return t }
const hhmm = (t) => `${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`

function AlarmSheet({ onSet, onClose }) {
  const [mins, setMins] = useState(60)
  const until = clockAfter(mins)
  const tomorrow = until.toDateString() !== new Date().toDateString()
  return (
    <Sheet onClose={onClose}>
      <h3 style={{ textAlign: 'center' }}>몇 시까지 끌까요?</h3>
      <div className="readout" aria-live="polite"><span className="jua">{tomorrow && <small>내일 </small>}{hhmm(until)}</span><small>까지</small></div>
      <input className="range" type="range" min={STEP} max={1440} step={STEP} value={mins} style={{ '--p': `${((mins - STEP) / (1440 - STEP)) * 100}%` }} onChange={(e) => setMins(+e.target.value)} aria-label="끌 시간" />
      <button className="sheetbar" onClick={() => onSet(until.toISOString())}>끄기</button>
    </Sheet>
  )
}

export function Messages({ me, room, d, clearUnread, onOpen, onRoom, onGo, alarm, reload }) {
  const [ask, setAsk] = useState(false)
  const [checking, setChecking] = useState(null) // 방금 체크한 메시지 (잠깐 체크 표시를 보이고 목록에서 뺀다)
  const [gone, setGone] = useState([])
  const check = (id) => {
    setChecking(id)
    setTimeout(async () => {
      setGone((g) => [...g, id]); setChecking(null)
      try { await api(`/teacher/messages/${id}/done`, { method: 'POST', body: { done: true } }); reload?.() } catch { setGone((g) => g.filter((x) => x !== id)) }
    }, 350)
  }
  useEffect(() => { clearUnread() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <div className="app"><Loading /></div>
  const urgent = d.todo.urgent.filter((u) => !gone.includes(u.id))
  const replies = alarm.off ? [] : d.todo.items.filter((m) => !gone.includes(m.id)) // 알림을 끄면 일반 연락은 숨기고 긴급 · 안전만 남긴다
  const sent = alarm.off ? 0 : d.school.counts.school // 공격적 표현은 학교(관리자)가 맡고, 담임에게는 건수만 보인다
  const todayIso = new Date(Date.now() - new Date().getTimezoneOffset() * 6e4).toISOString().slice(0, 10)
  const chores = [] // 담임이 오늘 챙길 것: 알림장을 아직 안 올렸을 때 · 열려 있는 상담의 예약 현황
  if (!alarm.off && d.notebooks && !d.notebooks.some((n) => n.day === todayIso)) chores.push({ title: '오늘 알림장', sub: '아직 안 올렸어요', go: () => onGo('알림장', 'notebook') })
  if (!alarm.off) d.counsel.filter((s) => s.open).forEach((s) => chores.push({ title: `${s.title} 예약`, sub: `${s.booked} / ${s.total}칸`, go: () => onGo('상담') }))
  return (
    <div className="app">
      <SectionHead title="쿠션톡" quiet={alarm.off} extra={<AlarmSwitch alarm={alarm} onAsk={() => setAsk(true)} />}>
        {room && <ClassHead grade={room.grade} classNo={room.class_no} sub={`${me.school_name || ''} · 학생 ${room.student_count}명`} icon="반 톡방" label="톡방" onAct={onRoom} />}
      </SectionHead>
      <div className="page tight" style={{ paddingTop: 10 }}>
        {chores.length > 0 && (
          <>
            <div className="band"><span>오늘 할 일</span><span>{chores.length}</span></div>
            <div className="ls">{chores.map((c) => (
              <button key={c.title} className="li" onClick={c.go}><div className="g"><b>{c.title}</b><p>{c.sub}</p></div><span className="go">›</span></button>))}</div>
          </>
        )}
        {(urgent.length + replies.length === 0
          ? <Empty title={alarm.off ? '알림 꺼짐' : '답장할 연락 없음'} />
          : <div className="ls">
              {urgent.map((u) => (
                <div key={u.id} className="li urg">
                  <button className={`cb${checking === u.id ? ' on' : ''}`} onClick={() => check(u.id)} role="checkbox" aria-checked={checking === u.id} aria-label="확인">{checking === u.id && <Ic name="tick" size={14} />}</button>
                  <div className="g" style={{ cursor: 'pointer' }} onClick={() => onOpen(u.id)}><Chip kind="coral">긴급 · {URGENT[u.urgent_type]}</Chip>
                    <b style={{ display: 'block', marginTop: 5 }}>{u.child_name} 보호자 · 원문 그대로</b><p>{u.preview}…</p></div><span className="go" onClick={() => onOpen(u.id)}>›</span>
                </div>))}
              {replies.map((m) => <MsgRow key={m.id} m={m} onClick={() => onOpen(m.id)} onDone={check} checking={checking === m.id} />)}
            </div>)}
        {sent > 0 && <div className="band"><span>학교로 이관</span><span>{sent}</span></div>}
      </div>
      {ask && <AlarmSheet onClose={() => setAsk(false)} onSet={async (iso) => { await alarm.set(iso); setAsk(false) }} />}
    </div>
  )
}

// ───────── 출결: 열면 모두 읽음 (건별 확인 버튼 없음) ─────────
export function Attendance({ d, reload }) {
  const [kind, setKind] = useState('absent')
  const pending = d?.att.pending ?? 0
  useEffect(() => {
    if (pending > 0) api('/teacher/attendance/check-all', { method: 'POST' }).then(reload).catch(() => {})
  }, [pending]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <div className="app"><Loading /></div>
  const att = d.att
  return (
    <div className="app">
      <SectionHead title="출결" side={dateText(att.day)}>
        <div className="nbtns" style={{ padding: '6px 16px 12px' }}>
          {[['absent', 'b'], ['early', 's'], ['late', 'c']].map(([k, c]) => (
            <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>
              <span className={`qic ${c}`}><Ic name={k} size={20} /></span>
              <span className="t">{ATT_KIND[k]}<span className="n">{att.counts[k]}</span></span>
            </button>))}
        </div>
      </SectionHead>
      <div className="page tight" style={{ paddingTop: 4 }}>
        {[kind, 'result'].map((key, idx) => {
          const list = att.items.filter((i) => i.kind === key)
          if (idx === 1 && !list.length) return null
          return (
            <div key={key} style={{ display: 'contents' }}>
              <div className="band"><span>{ATT_KIND[key]}</span><span>{list.length}</span></div>
              {list.length > 0 && <div className="ls">{list.map((i) => (
                    <div key={i.id} className="li"><div className="g"><div className="rowc"><b>{i.child_name}</b><Chip kind="line">{i.detail}</Chip></div>{i.reason && <p>{i.reason}</p>}</div></div>))}</div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ───────── 승인: 체험학습 신청서 ─────────
export function Approvals({ d, onTrip }) {
  if (!d) return <div className="app"><Loading /></div>
  const pending = d.trips.filter((t) => t.status === 'pending')
  const done = d.trips.filter((t) => t.status !== 'pending')
  const row = (t) => (
    <button key={t.id} className="li" onClick={() => onTrip(t)}>
      <div className="g"><div className="rowc"><b>{t.child_name} · 체험학습</b>{t.status === 'pending' ? <Chip kind="mint">신청</Chip> : <Chip kind={TRIP[t.status][0]}>{TRIP[t.status][1]}</Chip>}</div>
        <p>{t.start_date.slice(5)} ~ {t.end_date.slice(5)} · {t.place}</p></div><span className="go">›</span>
    </button>
  )
  return (
    <div className="app">
      <SectionHead title="승인" />
      <div className="page tight" style={{ paddingTop: 6 }}>
        {pending.length + done.length === 0 && <Empty title="승인할 신청 없음" />}
        {pending.length > 0 && <div className="ls">{pending.map(row)}</div>}
        {done.length > 0 && <><div className="band"><span>처리한 것</span><span>{done.length}</span></div><div className="ls">{done.map(row)}</div></>}
      </div>
    </div>
  )
}

// 체험학습 신청서 보기 · 승인 / 반려 (꽉 찬 하단 바)
export function TripDetail({ trip, onBack }) {
  const [note, setNote] = useState(trip.note || '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const open = trip.status === 'pending'
  const decide = async (decision) => {
    setBusy(true); setErr(null)
    try { await api(`/teacher/field-trips/${trip.id}/decision`, { method: 'POST', body: { decision, note } }); onBack() }
    catch (e) { setErr(e.message); setBusy(false) }
  }
  const kv = (k, v) => <div className="kv2"><span>{k}</span><b>{v}</b></div>
  return (
    <div className="app">
      <div className="hdr"><button className="back" onClick={onBack} aria-label="뒤로">‹</button><div className="f1"><b>체험학습 신청서</b></div></div>
      <div className="page tight" style={{ paddingBottom: 110 }}>
        <div className="row"><b style={{ fontSize: 18 }} className="grow">{trip.child_name}</b><Chip kind={TRIP[trip.status][0]}>{open ? '신청' : TRIP[trip.status][1]}</Chip></div>
        <div className="ls">{kv('기간', `${trip.start_date} ~ ${trip.end_date}`)}{kv('형태', trip.learn_type)}{kv('장소', trip.place)}{trip.stay && kv('숙박', trip.stay)}{kv('목적', trip.purpose)}</div>
        <div className="f"><label>메모</label>
          <textarea className="field" maxLength={200} disabled={!open} value={note} onChange={(e) => setNote(e.target.value)} /></div>
        {err && <p className="err" role="alert">{err}</p>}
      </div>
      {open && <div className="bar2"><button disabled={busy} onClick={() => decide('rejected')}>반려</button><button className="p" disabled={busy} onClick={() => decide('approved')}>승인</button></div>}
    </div>
  )
}
