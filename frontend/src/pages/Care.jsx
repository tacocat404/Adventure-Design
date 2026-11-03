// 알림장 · 상담 예약 화면 (11.04)
// 알림장: 준비물 · 과제 · 전달 세 칸 고정. 학부모가 "확인했어요"를 누르고, 교사는 확인 수만 본다.
// 상담: 선착순 예약. 교사가 날짜 · 시간대를 열면 학부모가 빈 칸을 골라 바로 확정한다. 내용은 보내기 전에 쿠션이가 살펴본다.
import { useEffect, useState } from 'react'
import { api, usePoll, dateText, today, dday } from '../api.js'
import { Btn, Chip, Cushi, Header, Ic, Loading, Marked, Sheet } from '../components/ui.jsx'

const NOTE = [['supplies', '준비물', 'butter'], ['homework', '과제', 'sky'], ['notice', '전달', 'mint']]
const WEEK = ['일', '월', '화', '수', '목', '금', '토']
const dayText = (iso) => { const d = new Date(`${iso}T00:00:00`); return `${d.getMonth() + 1}월 ${d.getDate()}일 (${WEEK[d.getDay()]})` }
const left = (n) => (n === 0 ? '오늘까지' : n > 0 ? `D-${n}` : '마감')

const Field = ({ label, children }) => <div className="f"><label>{label}</label>{children}</div>

// ───────── 알림장 한 장 (줄 세 개) ─────────
// 알림장 줄. onToggle이 있으면 항목마다 체크(투두)가 붙는다 (학부모 · 학생), 없으면 읽기만 (교사)
export function NotebookRows({ n, onToggle }) {
  return NOTE.filter(([k]) => n[k]).map(([k, label, kind]) => {
    if (!onToggle) return <div key={k} className="li"><Chip kind={kind}>{label}</Chip><div className="g">{n[k]}</div></div>
    const done = n.checks?.includes(k)
    return (
      <button key={k} className="li" onClick={() => onToggle(n.id, k, !done)} role="checkbox" aria-checked={!!done}>
        <span className={`cb${done ? ' on' : ''}`}>{done && <Ic name="tick" size={14} />}</span>
        <Chip kind={kind}>{label}</Chip><div className={`g txt${done ? ' done' : ''}`}>{n[k]}</div>
      </button>
    )
  })
}

const checkItem = (reload) => async (id, item, done) => { await api(`/notebooks/${id}/check`, { method: 'POST', body: { item, done } }); reload() }

// 학부모 홈의 "오늘 알림장" + 확인했어요
export function TodayNotebook({ classId, readonly }) {
  const [d, setD] = useState(null)
  const load = async () => setD(await api(`/classes/${classId}/notebooks`))
  usePoll(load, [classId])
  const n = d?.items[0]
  if (!n || n.day !== today()) return null
  const read = async () => { await api(`/notebooks/${n.id}/read`, { method: 'POST' }); load() }
  return (
    <>
      <div className="band"><span>오늘 알림장 · {dayText(n.day)}</span>{readonly ? null : n.mine ? <span>확인함</span> : <span style={{ color: 'var(--coral-deep)' }}>확인 전</span>}</div>
      <div className="ls nblist"><NotebookRows n={n} onToggle={checkItem(load)} /></div>
      {!readonly && <button className="readbtn" disabled={n.mine} onClick={read}>{n.mine ? '확인함' : '확인했어요'}</button>}
    </>
  )
}

// 알림장 목록 (학부모: 확인 버튼 · 교사: 확인 수)
export function NotebookList({ classId, teacher, readonly }) {
  const [d, setD] = useState(null)
  const load = async () => setD(await api(`/classes/${classId}/notebooks`))
  usePoll(load, [classId])
  if (!d) return null
  const read = async (id) => { await api(`/notebooks/${id}/read`, { method: 'POST' }); load() }
  if (!d.items.length) return null
  return d.items.map((n) => (
    <div key={n.id} style={{ display: 'contents' }}>
      <div className="band"><span>{dayText(n.day)}</span>
        {teacher ? <span>확인 {n.read_count} / {d.parent_total}</span>
          : readonly ? null : n.mine ? <span>확인함</span> : <button style={{ color: 'var(--coral-deep)', font: 'inherit', fontWeight: 800 }} onClick={() => read(n.id)}>확인했어요</button>}</div>
      <div className="ls nblist"><NotebookRows n={n} onToggle={teacher ? null : checkItem(load)} /></div>
    </div>
  ))
}

export function NotebookSheet({ classId, onClose }) {
  const [f, setF] = useState({ supplies: '', homework: '', notice: '' })
  const [again, setAgain] = useState(false) // 오늘 이미 올린 알림장이면 내용을 채워 고치게 한다
  const [err, setErr] = useState(null)
  useEffect(() => {
    api(`/classes/${classId}/notebooks`).then((d) => { const n = d.items.find((x) => x.day === today()); if (n) { setF({ supplies: n.supplies, homework: n.homework, notice: n.notice }); setAgain(true) } }).catch(() => {})
  }, [classId])
  const send = async () => { try { await api('/teacher/notebooks', { method: 'POST', body: { class_id: classId, ...f } }); onClose() } catch (e) { setErr(e.message) } }
  return (
    <Sheet onClose={onClose}>
      <h3 style={{ textAlign: 'center' }}>{again ? '알림장 고치기' : '알림장'} · {dayText(today())}</h3>
      {NOTE.map(([k, label]) => <Field key={k} label={label}><input className="field" maxLength={100} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>)}
      {err && <p className="err" role="alert">{err}</p>}
      <Btn disabled={!(f.supplies.trim() || f.homework.trim() || f.notice.trim())} onClick={send}>{again ? '고치기' : '올리기'}</Btn>
    </Sheet>
  )
}

// ───────── 상담: 교사 만들기 · 예약 현황 ─────────
export function CounselSheet({ classId, onClose }) {
  const [f, setF] = useState({ title: '2학기 학부모 상담', apply_to: new Date(Date.now() + 3 * 864e5 - new Date().getTimezoneOffset() * 6e4).toISOString().slice(0, 10), start_time: '14:00', end_time: '18:30', minutes: 30 })
  const [days, setDays] = useState([])
  const [pick, setPick] = useState(today())
  const [err, setErr] = useState(null)
  const send = async () => {
    try { await api('/teacher/counsel', { method: 'POST', body: { class_id: classId, apply_from: today(), ...f, minutes: +f.minutes, days } }); onClose() } catch (e) { setErr(e.message) }
  }
  return (
    <Sheet onClose={onClose}>
      <h3 style={{ textAlign: 'center' }}>상담 열기</h3>
      <Field label="제목"><input className="field" maxLength={40} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
      <Field label="신청 마감일"><input className="field" type="date" value={f.apply_to} min={today()} onChange={(e) => setF({ ...f, apply_to: e.target.value })} /></Field>
      <Field label="상담 날짜">
        <div className="row"><input className="field" type="date" value={pick} min={today()} onChange={(e) => setPick(e.target.value)} />
          <button type="button" className="btn b-white sm flat" onClick={() => pick && !days.includes(pick) && setDays([...days, pick].sort())}>추가</button></div>
        {days.length > 0 && <div className="tags">{days.map((d) => <button key={d} type="button" onClick={() => setDays(days.filter((x) => x !== d))}><Chip kind="sky">{dayText(d)} ✕</Chip></button>)}</div>}
      </Field>
      <div className="row">
        <div className="f grow"><label>시작</label><input className="field" type="time" value={f.start_time} onChange={(e) => setF({ ...f, start_time: e.target.value })} /></div>
        <div className="f grow"><label>끝</label><input className="field" type="time" value={f.end_time} onChange={(e) => setF({ ...f, end_time: e.target.value })} /></div>
        <div className="f grow"><label>한 가정</label><select className="sel" value={f.minutes} onChange={(e) => setF({ ...f, minutes: e.target.value })}>{[15, 20, 30, 40, 60].map((m) => <option key={m} value={m}>{m}분</option>)}</select></div>
      </div>
      {err && <p className="err" role="alert">{err}</p>}
      <Btn disabled={!f.title.trim() || !days.length} onClick={send}>상담 열기</Btn>
    </Sheet>
  )
}

export function CounselStatus({ classId }) {
  const [d, setD] = useState(null)
  const load = async () => setD(await api(`/classes/${classId}/counsel`))
  usePoll(load, [classId])
  const [sure, setSure] = useState(null) // 취소는 두 번 눌러야 한다 (조건부 반환보다 위에 둬야 훅 순서가 안 깨진다)
  if (!d) return null
  if (!d.items.length) return null
  const cancel = async (id) => {
    if (sure !== id) return setSure(id)
    await api(`/counsel/bookings/${id}/cancel`, { method: 'POST' }); setSure(null); load()
  }
  return d.items.map((s) => (
    <div key={s.id} style={{ display: 'contents' }}>
      <div className="chunk" style={{ margin: '4px 0' }}>
        <div className="tags" style={{ marginTop: 0 }}><Chip kind="sky">상담</Chip>{s.open ? <Chip kind="mint">진행중</Chip> : <Chip>마감</Chip>}{s.open && <Chip kind="due">{left(s.days_left)}</Chip>}</div>
        <p className="tt" style={{ fontWeight: 800, marginTop: 8 }}>{s.title}</p>
        <p className="cap">{s.days.map((x) => x.day.slice(5)).join(' · ')} · {s.start_time}~{s.end_time} · {s.minutes}분</p>
        <div className="bar" style={{ marginTop: 8 }}><i style={{ width: `${s.total ? (s.booked / s.total) * 100 : 0}%` }} /></div>
        <p className="cap" style={{ textAlign: 'right', marginTop: 4 }}>예약 {s.booked} / {s.total}칸</p>
      </div>
      {s.days.map((day) => {
        const list = s.bookings.filter((b) => b.day === day.day)
        return (
          <div key={day.day} style={{ display: 'contents' }}>
            <div className="band"><span>{dayText(day.day)}</span><span>{list.length} / {day.slots.length}</span></div>
            {list.length > 0 && <div className="ls">{list.map((b) => (
              <div key={b.id} className="li"><div className="g"><div className="rowc"><b>{b.slot}</b><b>{b.child_name}</b>{b.masked_count > 0 && <Chip kind="butter">{b.masked_count}곳 가림</Chip>}</div><p>{b.content_masked}</p></div>
                <button className="cap" style={{ fontWeight: 800, color: sure === b.id ? 'var(--coral-deep)' : undefined }} onClick={() => cancel(b.id)}>{sure === b.id ? '취소 확인' : '취소'}</button></div>))}</div>}
          </div>
        )
      })}
    </div>
  ))
}

// ───────── 상담: 학부모 예약 ─────────
function useGuard() {
  const [stage, setStage] = useState(null)
  const [warn, setWarn] = useState(null)
  const guard = async (text, send) => {
    setStage('checking')
    const r = await Promise.race([api('/parent/precheck', { method: 'POST', body: { text } }).catch(() => null), new Promise((x) => setTimeout(() => x(null), 5000))])
    setStage(null)
    if (r?.rough) setWarn({ ...r, text, send }); else send(text)
  }
  const sheet = warn && (
    <Sheet warn onClose={() => setWarn(null)}>
      <h3>이 표현은 교권 침해로 기록될 수 있어요</h3>
      <div className="quote"><Marked text={warn.text} spans={warn.spans} /></div>
      {warn.suggestions.slice(0, 1).map((s, i) => <Btn key={i} onClick={() => { const w = warn; setWarn(null); w.send(s.slice(0, 200)) }}>바꾼 문장으로 예약하기</Btn>)}
      <div className="two"><Btn kind="white" onClick={() => setWarn(null)}>직접 고치기</Btn>
        <button className="btn b-ghost" onClick={() => { const w = warn; setWarn(null); w.send(w.text) }}>그대로 예약하기</button></div>
    </Sheet>
  )
  return { guard, stage, sheet }
}

export function CounselBook({ cls, onBack }) {
  const [list, setList] = useState(null)
  const [day, setDay] = useState(null)
  const [slot, setSlot] = useState(null)
  const [content, setContent] = useState('')
  const [err, setErr] = useState(null)
  const [done, setDone] = useState(null)
  const [busy, setBusy] = useState(false)
  const { guard, stage, sheet } = useGuard()
  const load = async () => setList((await api(`/classes/${cls.class_id}/counsel`)).items)
  usePoll(load, [cls.class_id], 5000) // 선착순이라 자주 새로 고침: 남이 잡은 칸이 바로 회색이 된다
  const s = list?.find((x) => x.open) || list?.[0]
  const cur = s?.days.find((x) => x.day === (day || s.days[0]?.day))
  const book = (text) => async () => {}
  const send = async (text) => {
    setBusy(true); setErr(null)
    try { setDone(await api(`/parent/counsel/${s.id}/book`, { method: 'POST', body: { day: cur.day, slot, content: text } })); load() }
    catch (e) { setErr(e.message); setSlot(null); load() } finally { setBusy(false) }
  }
  const cancel = async () => { await api(`/counsel/bookings/${s.mine.id}/cancel`, { method: 'POST' }); setDone(null); setSlot(null); load() }

  const head = <Header onBack={onBack} title="상담 예약" sub={`${cls.grade}학년 ${cls.class_no}반 · ${cls.child_name}`} />
  if (!list) return <div className="app">{head}<Loading /></div>
  if (!s) return <div className="app">{head}<div className="page"><div className="empty"><span className="ring"><Ic name="check" size={32} /></span><b>열린 상담이 없어요</b></div></div></div>
  const mine = done || s.mine
  if (mine) {
    return (
      <div className="app">{head}
        <div className="page tight">
          <div className="empty"><Cushi face="safe" size={90} /><b>예약했어요</b></div>
          <div className="ls">
            <div className="li"><div className="g sub2">일시</div><b>{dayText(mine.day)} {mine.slot}</b></div>
            <div className="li"><div className="g sub2">시간</div><b>{s.minutes}분</b></div>
          </div>
        </div>
        <div className="bar2"><button onClick={cancel}>예약 취소</button><button className="p" onClick={onBack}>돌아가기</button></div>
      </div>
    )
  }
  return (
    <div className="app">{head}
      <div className="page tight" style={{ paddingBottom: 110 }}>
        <div className="tags" style={{ marginTop: 0 }}><Chip kind="sky">상담</Chip>{s.open ? <Chip kind="mint">진행중</Chip> : <Chip>마감</Chip>}<Chip kind="due">{left(s.days_left)}</Chip></div>
        <b style={{ fontSize: 18 }}>{s.title}</b>
        {!s.open && <p className="err">{s.days_left < 0 ? '신청이 끝났어요' : '아직 신청 기간이 아니에요'}</p>}
        <p className="cap">신청 {s.apply_from.slice(5).replace('-', '/')} ~ {s.apply_to.slice(5).replace('-', '/')} · 한 가정 {s.minutes}분 · 선착순</p>
        <div className="band"><span>날짜</span></div>
        <div className="seg" style={{ padding: '4px 0' }}>{s.days.map((x) => <button key={x.day} type="button" className={cur.day === x.day ? 'on' : ''} onClick={() => { setDay(x.day); setSlot(null) }}>{dayText(x.day)}</button>)}</div>
        <div className="band"><span>시간</span><span>{slot ? `선택 ${slot}` : '선택 0'}</span></div>
        <div className="slots">{cur.slots.map((t) => (
          <button key={t.time} type="button" disabled={t.taken} className={`slot${slot === t.time ? ' on' : ''}${t.taken ? ' x' : ''}`} onClick={() => setSlot(t.time)}>{t.time}</button>))}</div>
        <div className="band"><span>상담 내용</span><span>{content.length}/200</span></div>
        <textarea className="rowarea" maxLength={200} value={content} onChange={(e) => setContent(e.target.value)} aria-label="상담 내용" />
        {stage === 'checking' && <div className="row cap"><Cushi face="read" size={30} />확인 중</div>}
        {err && <p className="err" role="alert">{err}</p>}
      </div>
      <div className="bar2"><button className="p" disabled={!s.open || !slot || !content.trim() || busy || !!stage} onClick={() => guard(content, send)}>예약하기</button></div>
      {sheet}
    </div>
  )
}

// 신청 탭 · 홈에서 쓰는 내 예약 한 줄 정보
export function useMyCounsel(classId) {
  const [s, setS] = useState(null)
  usePoll(async () => {
    if (!classId) return
    const items = (await api(`/classes/${classId}/counsel`)).items
    setS(items.find((x) => x.open) || items[0] || null)
  }, [classId])
  return s
}
export const counselChip = (s) => (s?.mine ? { kind: 'mint', text: '예약함' } : s?.open ? { kind: 'due', text: left(s.days_left) } : null)
export { dayText, left }
