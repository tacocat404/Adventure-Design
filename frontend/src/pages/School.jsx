// 학교 생활 화면 (11.04 하이클래스 반영) — 학부모: 홈 · 출결 알리기 · 양식 신청 · 학교소식 · 설문 / 교사: 출결 · 공지 · 설문
// 이 화면들은 AI를 거치지 않는다. 사유 칸만 보내기 전 검사(쿠션이)를 한 번 거친다.
import { useEffect, useState } from 'react'
import { api, usePoll, ATT_KIND, ATT_DETAIL, NOTICE_KIND, LEARN_TYPES, today, dateText, when } from '../api.js'
import { Btn, Chip, ClassHead, Cushi, Dot, Header, Ic, Loading, Marked, Sheet, Title } from '../components/ui.jsx'
import { SectionHead } from './TeacherHome.jsx'
import { CounselSheet, CounselStatus, NotebookList, NotebookSheet, TodayNotebook, counselChip, dayText, useMyCounsel } from './Care.jsx'

const Field = ({ label, need, count, children }) => (
  <div className="f"><label>{label}{need && <em> *</em>}{count && <small>{count}</small>}</label>{children}</div>
)
const Seg = ({ items, on, onPick }) => (
  <div className="seg">{items.map(([k, v]) => <button key={k} type="button" className={on === k ? 'on' : ''} onClick={() => onPick(k)}>{v}</button>)}</div>
)
const ddayText = (n) => (n === 0 ? '오늘까지' : n > 0 ? `D-${n}` : '마감')

// 교사 첫 반의 id (공지 · 설문은 담임 반에 올린다)
export function useTeacherClass() {
  const [room, setRoom] = useState(null)
  useEffect(() => { api('/teacher/rooms').then((r) => setRoom(r.rooms[0] ?? null)).catch(() => {}) }, [])
  return room // { class_id, grade, class_no, ... }
}

// ───────── 학부모 홈 (4분면 + 오늘). 내 정보는 상단 사람 아이콘, 신청 내역은 신청 탭 ─────────
export function Home({ me, cls, go, unread = 0 }) {
  const [d, setD] = useState(null)
  usePoll(async () => { if (cls) setD(await api(`/classes/${cls.class_id}/today`)) }, [cls?.class_id])
  const cs = useMyCounsel(cls?.class_id)
  const chip = counselChip(cs)
  if (!cls) {
    return (
      <div className="app"><SectionHead title="쿠션톡" />
        <div className="page"><Btn onClick={() => go('연락')}>선생님 고르기</Btn></div></div>
    )
  }
  const day = new Date()
  return (
    <div className="app">
      <SectionHead title="쿠션톡">
        <ClassHead grade={cls.grade} classNo={cls.class_no} sub={`${me.school_name || ''} · ${cls.teacher_name} 선생님`} icon="연락" label="연락" onAct={() => go('연락')} />
      </SectionHead>
      <div className="page" style={{ paddingTop: 6 }}>
        <div className="cxr"><Cushi face="hi" size={64} /><div className="say">{cls.child_name} 보호자님, 안녕하세요!</div></div>
        <div className="quick">
          <button onClick={() => go('연락')}><span className="qic s"><Ic name="연락" /></span>선생님께 연락<Dot n={unread} /></button>
          <button onClick={() => go('att')}><span className="qic b"><Ic name="출결" /></span>출결 알리기</button>
          <button onClick={() => go('trip')}><span className="qic m"><Ic name="양식" /></span>양식 신청</button>
          <button onClick={() => go('counsel')}><span className="qic c"><Ic name="상담" /></span>상담 예약
            {chip && <Chip kind={chip.kind}>{chip.text}</Chip>}</button>
        </div>
        <TodayNotebook classId={cls.class_id} />
        {d && (
          <>
            <p className="sec">오늘</p>
            <div className="chunk">
              <div className="row"><b>{day.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'long' })}</b>
                <span className="t">시간표 · 급식</span></div>
              <div style={{ marginTop: 6 }}>{d.timetable.map((s, i) => <div className="tt-row" key={i}><i>{i + 1}</i>{s}</div>)}</div>
              <p className="cap" style={{ marginTop: 6 }}>급식 · {d.meal.join(' · ')}</p>
            </div>
            {d.new_notices > 0 && <button className="chunk pin" onClick={() => go('소식')}><b>새 학교소식 {d.new_notices}개</b></button>}
          </>
        )}
      </div>
    </div>
  )
}

// ───────── 신청 탭: 작성하기 · 응답할 것 · 내 신청 내역 ─────────
export function Apply({ cls, go }) {
  const [surveys, setSurveys] = useState([])
  const [trips, setTrips] = useState([])
  const [atts, setAtts] = useState([])
  const cs = useMyCounsel(cls?.class_id)
  usePoll(async () => {
    if (!cls) return
    setSurveys((await api(`/classes/${cls.class_id}/surveys`)).items)
    setTrips((await api(`/parent/classes/${cls.class_id}/field-trips`)).items)
    setAtts((await api(`/parent/classes/${cls.class_id}/attendance`)).items)
  }, [cls?.class_id])
  if (!cls) return <div className="app"><SectionHead title="신청" /><div className="page"><Btn onClick={() => go('연락')}>선생님 고르기</Btn></div></div>
  const todo = surveys.filter((x) => x.open && x.my_answer == null)
  const row = (ic, c, title, onClick) => (
    <button className="li" onClick={onClick}><span className={`qic ${c}`}><Ic name={ic} size={20} /></span><div className="g"><b>{title}</b></div><span className="go">›</span></button>
  )
  const TRIP = { pending: ['coral', '대기'], approved: ['mint', '승인'], rejected: ['slate', '반려'] }
  return (
    <div className="app">
      <SectionHead title="신청" />
      <div className="page tight" style={{ paddingTop: 6 }}>
        <div className="band"><span>작성하기</span></div>
        <div className="ls">{row('출결', 'b', '출결 알리기', () => go('att'))}{row('양식', 'm', '체험학습 신청서', () => go('trip'))}{row('상담', 'c', '상담 예약', () => go('counsel'))}</div>
        {todo.length > 0 && <div className="band"><span>응답할 것</span><span>{todo.length}</span></div>}
        {todo.length > 0 && <div className="ls">{todo.map((x) => (
          <button key={x.id} className="li" onClick={() => go('survey')}><span className="qic c"><Ic name="설문" size={20} /></span>
            <div className="g"><b>{x.title}</b><p>{ddayText(x.days_left)} · 필수</p></div><span className="go">›</span></button>))}</div>}
        <div className="band"><span>내 신청 내역</span></div>
        <div className="ls">
          {cs?.mine && <button className="li" onClick={() => go('counsel')}><div className="g"><b>상담 · {cs.title}</b><p>{dayText(cs.mine.day)} {cs.mine.slot}</p></div><Chip kind="mint">예약함</Chip></button>}
          {trips.map((t) => (
            <div key={`t${t.id}`} className="li"><div className="g"><b>체험학습 · {t.place}</b><p>{t.start_date.slice(5)} ~ {t.end_date.slice(5)}{t.note ? ` · ${t.note}` : ''}</p></div>
              <Chip kind={TRIP[t.status][0]}>{TRIP[t.status][1]}</Chip></div>))}
          {atts.map((a) => (
            <div key={`a${a.id}`} className="li"><div className="g"><b>{ATT_KIND[a.kind]} · {a.detail}</b><p>{dateText(a.att_date)}</p></div>
              {a.checked_at ? <Chip kind="mint">확인</Chip> : <Chip kind="coral">대기</Chip>}</div>))}
        </div>
      </div>
    </div>
  )
}

// 목록형 폼 부품: 이름 · 오른쪽 값 · › (탭하면 선택 시트) / 입력 행
function PickRow({ label, current, options, onPick }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" className="li" onClick={() => setOpen(true)}><div className="g sub2">{label}</div>
        <span className="val">{options.find(([k]) => k === current)?.[1]}</span><span className="go">›</span></button>
      {open && (
        <Sheet onClose={() => setOpen(false)}>
          <h3 style={{ textAlign: 'center' }}>{label}</h3>
          <div className="ls" style={{ margin: '0 -20px' }}>
            {options.map(([k, v]) => (
              <button key={k} type="button" className="li" style={{ padding: '14px 20px' }} onClick={() => { onPick(k); setOpen(false) }}>
                <div className="g"><b>{v}</b></div>{current === k && <span className="ok"><Ic name="check" size={18} /></span>}</button>))}
          </div>
        </Sheet>
      )}
    </>
  )
}
const InRow = ({ label, need, children }) => <label className="li"><span className="sub2">{label}{need && <em>*</em>}</span>{children}</label>

// ───────── 출결 알리기 (목록형) ─────────
export function AttendanceForm({ cls, onBack }) {
  const [kind, setKind] = useState('absent')
  const [date, setDate] = useState(today())
  const [detail, setDetail] = useState('질병')
  const [reason, setReason] = useState('')
  const [stage, setStage] = useState(null)
  const [warn, setWarn] = useState(null)
  const [done, setDone] = useState(false)
  const [err, setErr] = useState(null)

  const send = async (text) => {
    setStage('sending'); setWarn(null); setErr(null)
    try { await api('/parent/attendance', { method: 'POST', body: { class_id: cls.class_id, kind, att_date: date, detail, reason: text } }); setDone(true) }
    catch (e) { setErr(e.message) } finally { setStage(null) }
  }
  const check = async () => {
    if (!reason.trim()) return send('')
    setStage('checking')
    const r = await Promise.race([api('/parent/precheck', { method: 'POST', body: { text: reason } }).catch(() => null), new Promise((x) => setTimeout(() => x(null), 5000))])
    if (r?.rough) { setStage(null); setWarn({ ...r, text: reason }) } else send(reason)
  }

  if (done) {
    return (
      <div className="app"><Header onBack={onBack} title="출결 알리기" />
        <div className="page"><div className="empty"><Cushi face="safe" size={96} /><b>선생님께 전했어요</b>
          <p className="cap">{cls.child_name} · {dateText(date)} · {ATT_KIND[kind]}</p></div><Btn onClick={onBack}>돌아가기</Btn></div></div>
    )
  }
  return (
    <div className="app">
      <Header onBack={onBack} title="출결 알리기" sub={`${cls.grade}학년 ${cls.class_no}반 · ${cls.child_name}`} />
      <div className="page tight" style={{ paddingBottom: 110 }}>
        <div className="ls">
          <PickRow label="출결 구분" current={kind} options={Object.entries(ATT_KIND)} onPick={setKind} />
          <InRow label="출결일"><input className="rowin blue" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></InRow>
          <PickRow label="상세 구분" current={detail} options={ATT_DETAIL.map((v) => [v, v])} onPick={setDetail} />
        </div>
        <div className="band"><span>사유</span><span>{reason.length}/100</span></div>
        <textarea className="rowarea" maxLength={100} value={reason} onChange={(e) => setReason(e.target.value)} aria-label="사유" />
        {stage === 'checking' && <div className="row cap"><Cushi face="read" size={30} />확인 중</div>}
        {err && <p className="err" role="alert">{err}</p>}
      </div>
      <div className="bar2"><button className="p" disabled={!!stage || !date} onClick={check}>{stage === 'sending' ? '보내는 중…' : '선생님께 알리기'}</button></div>
      {warn && (
        <Sheet warn onClose={() => setWarn(null)}>
          <h3>이 표현은 교권 침해로 기록될 수 있어요</h3>
          <div className="quote"><Marked text={warn.text} spans={warn.spans} /></div>
          {warn.suggestions.slice(0, 1).map((s, i) => <Btn key={i} onClick={() => send(s.slice(0, 100))}>바꾼 문장으로 보내기</Btn>)}
          <div className="two"><Btn kind="white" onClick={() => setWarn(null)}>직접 고치기</Btn>
            <button className="btn b-ghost" onClick={() => send(warn.text)}>그대로 보내기</button></div>
        </Sheet>
      )}
    </div>
  )
}

// ───────── 체험학습 신청서 (목록형) ─────────
export function FieldTripForm({ cls, onBack }) {
  const [f, setF] = useState({ start_date: today(), end_date: today(), learn_type: '가족여행', place: '', stay: '', purpose: '' })
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const ok = f.place.trim() && f.purpose.trim() && f.end_date >= f.start_date
  const submit = async () => {
    setBusy(true); setErr(null)
    try { await api('/parent/field-trips', { method: 'POST', body: { class_id: cls.class_id, ...f } }); setDone(true) }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  if (done) {
    return (
      <div className="app"><Header onBack={onBack} title="체험학습 신청서" />
        <div className="page"><div className="empty"><Cushi face="safe" size={96} /><b>신청서를 냈어요</b><p className="cap">{f.start_date} ~ {f.end_date} · {f.place}</p></div>
          <Btn onClick={onBack}>돌아가기</Btn></div></div>
    )
  }
  return (
    <div className="app">
      <Header onBack={onBack} title="체험학습 신청서" sub={cls.child_name} />
      <div className="page tight" style={{ paddingBottom: 110 }}>
        <div className="ls">
          <InRow label="시작일" need><input className="rowin blue" type="date" value={f.start_date} onChange={set('start_date')} /></InRow>
          <InRow label="종료일" need><input className="rowin blue" type="date" value={f.end_date} min={f.start_date} onChange={set('end_date')} /></InRow>
          <PickRow label="학습형태" current={f.learn_type} options={LEARN_TYPES.map((v) => [v, v])} onPick={(v) => setF({ ...f, learn_type: v })} />
          <InRow label="체험장소" need><input className="rowin" maxLength={30} value={f.place} onChange={set('place')} /></InRow>
          <InRow label="숙박장소"><input className="rowin" maxLength={30} value={f.stay} onChange={set('stay')} /></InRow>
        </div>
        <div className="band"><span>체험목적 *</span><span>{f.purpose.length}/30</span></div>
        <textarea className="rowarea" maxLength={30} value={f.purpose} onChange={set('purpose')} aria-label="체험목적" />
        {err && <p className="err" role="alert">{err}</p>}
      </div>
      <div className="bar2"><button className="p" disabled={!ok || busy} onClick={submit}>제출하기</button></div>
    </div>
  )
}

// ───────── 설문 (학부모는 답하기 · 교사는 결과 보기) ─────────
function Survey({ s, teacher, onChanged }) {
  const [pick, setPick] = useState(s.my_answer)
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (teacher) api(`/teacher/surveys/${s.id}/results`).then(setRes).catch(() => {}) }, [s.id, teacher])
  const save = async () => { setBusy(true); try { await api(`/surveys/${s.id}/answer`, { method: 'POST', body: { option_idx: pick } }); onChanged() } finally { setBusy(false) } }
  return (
    <div className="chunk">
      <div className="tags" style={{ marginTop: 0 }}><Chip kind="sky">설문</Chip>
        {s.open ? <Chip kind="mint">진행중</Chip> : <Chip>마감</Chip>}{s.open && <Chip kind="due">{ddayText(s.days_left)}</Chip>}</div>
      <p className="tt" style={{ fontWeight: 800, marginTop: 8 }}>{s.title}</p>
      <p className="cap">회신 기간 {s.opens_on.slice(5).replace('-', '.')} ~ {s.closes_on.slice(5).replace('-', '.')}</p>
      {s.body && <p className="sum" style={{ marginTop: 6 }}>{s.body}</p>}
      <div style={{ background: 'var(--bg)', borderRadius: 14, padding: '10px 12px', marginTop: 10 }}>
        <div className="tags" style={{ marginTop: 0 }}><Chip kind="coral">필수</Chip><Chip kind="sky">단일선택</Chip></div>
        <p style={{ fontWeight: 800, margin: '6px 0 2px' }}>{s.question}</p>
        {teacher
          ? s.options.map((o, i) => (
              <div key={i} style={{ padding: '5px 0' }}><div className="row"><span className="grow">{o}</span><b>{res?.counts[i] ?? 0}</b></div>
                <div className="bar"><i style={{ width: `${res?.total ? (res.counts[i] / res.total) * 100 : 0}%` }} /></div></div>))
          : s.options.map((o, i) => <button key={i} className={`rad${pick === i ? ' on' : ''}`} disabled={!s.open} onClick={() => setPick(i)}><span className="radio" />{o}</button>)}
      </div>
      {teacher
        ? <p className="cap" style={{ marginTop: 6 }}>{res ? `${res.total}명이 답했어요` : ''}</p>
        : s.open && <Btn className="sm" style={{ marginTop: 8, width: '100%' }} disabled={pick == null || pick === s.my_answer || busy} onClick={save}>{s.my_answer == null ? '제출하기' : s.my_answer === pick ? '제출했어요' : '답 바꾸기'}</Btn>}
    </div>
  )
}

// ───────── 학교소식 피드 (학부모 · 교사 같이 씀) ─────────
export function Feed({ classId, teacher, first = 'all', bare, student }) {
  const [kindState, setKind] = useState(first)
  const kind = bare ? first : kindState // bare: 위의 탭은 부르는 쪽이 갖는다
  const [items, setItems] = useState(null)
  const [surveys, setSurveys] = useState([])
  const [open, setOpen] = useState(null)
  const [viewImg, setViewImg] = useState(null) // 가정통신문 이미지 크게 보기
  const [sheet, setSheet] = useState(null) // notice · survey
  const load = async () => {
    if (!classId) return
    const q = kind !== 'all' && kind !== 'survey' ? `?kind=${kind}` : ''
    if (kind !== 'notebook' && kind !== 'counsel') setItems((await api(`/classes/${classId}/notices${q}`)).items)
    setSurveys((await api(`/classes/${classId}/surveys`)).items)
  }
  usePoll(load, [classId, kind])
  const scrap = async (n) => { await api(`/notices/${n.id}/scrap`, { method: 'POST' }); load() }
  const tabs = [['all', '전체'], ['notebook', '알림장'], ['circular', '가정통신문'], ['class', '학급공지'], ['notice', '공지사항'], ['survey', '설문']]
  const body = (
    <>
      {!bare && <div className="utabs">{tabs.filter(([k]) => !(student && k === 'survey')).map(([k, v]) => <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{v}</button>)}</div>}
      {kind === 'notebook' ? <NotebookList classId={classId} teacher={teacher} readonly={student} /> : kind === 'counsel' ? <CounselStatus classId={classId} /> : kind === 'survey'
        ? (surveys.length ? surveys.map((s) => <Survey key={s.id} s={s} teacher={teacher} onChanged={load} />) : null)
        : items && (items.length ? items.map((n) => <NoticePost key={n.id} n={n} open={open === n.id} onOpen={() => setOpen(open === n.id ? null : n.id)} onImage={setViewImg} onScrap={!teacher && !student ? () => scrap(n) : null} />)
          : null)}
    </>
  )
  const wait = !items && kind !== 'notebook' && kind !== 'counsel' && kind !== 'survey'
  const viewer = viewImg && <button className="imgview" onClick={() => setViewImg(null)} aria-label="닫기"><img src={viewImg} alt="가정통신문" /></button>
  if (bare) return <div className="page tight" style={{ paddingBottom: 104, paddingTop: 10 }}>{wait ? <Loading /> : body}{viewer}</div>
  return (
    <div className="app">
      <SectionHead title="학교소식" />
      <div className="page tight" style={{ paddingBottom: 104 }}>{wait ? <Loading /> : body}</div>
      {viewer}
    </div>
  )
}

export function NoticePost({ n, open, onOpen, onImage, onScrap }) {
  const d = new Date(n.created_at)
  const date = `${String(d.getFullYear()).slice(2)}.${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')} ${['일', '월', '화', '수', '목', '금', '토'][d.getDay()]}요일`
  return (
    <article className="post">
      <div className="phead"><span className="pav">{(n.school_name || '학')[0]}</span><div className="g"><b>{n.school_name}</b><small>{date}</small></div>{n.pinned && <Chip kind="due">고정</Chip>}</div>
      <button className="pbody" onClick={onOpen}>
        <span className={`pk k-${n.kind}`}>{NOTICE_KIND[n.kind]}</span>
        <span className="ptitle">{n.title}</span>
        {open && <span className="ptext">{n.body}</span>}
      </button>
      {n.image && <button className="pimg" onClick={() => onImage(n.image)} aria-label="이미지 크게 보기"><img src={n.image} alt={n.title} loading="lazy" /></button>}
      <div className="pfoot">{n.image ? <span><Ic name="첨부" size={16} />첨부파일 1개</span> : <span />}{onScrap && <button onClick={onScrap}><Ic name="스크랩" size={16} fill={n.scrapped ? 'currentColor' : 'none'} />{n.scrapped ? '스크랩함' : '스크랩'}</button>}</div>
    </article>
  )
}

export function NoticeSheet({ classId, onClose }) {
  const [f, setF] = useState({ kind: 'class', title: '', body: '', pinned: false })
  const [err, setErr] = useState(null)
  const send = async () => { try { await api('/teacher/notices', { method: 'POST', body: { class_id: classId, ...f } }); onClose() } catch (e) { setErr(e.message) } }
  return (
    <Sheet onClose={onClose}>
      <h3>공지 올리기</h3>
      <Field label="종류"><Seg items={Object.entries(NOTICE_KIND)} on={f.kind} onPick={(kind) => setF({ ...f, kind })} /></Field>
      <Field label="제목"><input className="field" maxLength={60} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
      <Field label="내용"><textarea className="field" style={{ minHeight: 110 }} maxLength={2000} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></Field>
      <button className="row" style={{ fontWeight: 700 }} onClick={() => setF({ ...f, pinned: !f.pinned })}><span className={`radio${f.pinned ? ' on' : ''}`} />반 맨 위에 고정하기</button>
      {err && <p className="err">{err}</p>}
      <Btn disabled={!f.title.trim() || !f.body.trim()} onClick={send}>올리기</Btn>
    </Sheet>
  )
}

export function SurveySheet({ classId, onClose }) {
  const [f, setF] = useState({ title: '', question: '', options: ['', '', '', ''] })
  const [err, setErr] = useState(null)
  const opts = f.options.map((o) => o.trim()).filter(Boolean)
  const send = async () => {
    try { await api('/teacher/surveys', { method: 'POST', body: { class_id: classId, title: f.title, question: f.question, options: opts, days: 7 } }); onClose() }
    catch (e) { setErr(e.message) }
  }
  return (
    <Sheet onClose={onClose}>
      <h3>설문 만들기</h3>
      <Field label="제목"><input className="field" maxLength={60} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
      <Field label="질문"><input className="field" maxLength={100} value={f.question} onChange={(e) => setF({ ...f, question: e.target.value })} /></Field>
      <Field label="선택지">
        {f.options.map((o, i) => <input key={i} className="field" style={{ marginBottom: 6 }} maxLength={30} value={o} onChange={(e) => setF({ ...f, options: f.options.map((x, j) => (j === i ? e.target.value : x)) })} />)}</Field>
      {err && <p className="err">{err}</p>}
      <Btn disabled={!f.title.trim() || !f.question.trim() || opts.length < 2} onClick={send}>올리기</Btn>
    </Sheet>
  )
}

// ───────── 교사 보내기 탭: 공지 · 설문 · 반 톡방, 만들기는 ＋ 하나 ─────────
export function Send({ me, classId, tab, setTab, initialSheet = null }) {
  const [plus, setPlus] = useState(false)
  const [sheet, setSheet] = useState(initialSheet)
  const [bump, setBump] = useState(0)
  const close = () => { setSheet(null); setBump(bump + 1) }
  const opts = [
    ['news', 'b', '공지', () => setSheet('notice')],
    ['양식', 'm', '알림장', () => setSheet('notebook')],
    ['설문', 'c', '설문', () => setSheet('survey')],
    ['상담', 's', '상담', () => setSheet('counsel')],
  ]
  return (
    <div className="app">
      <SectionHead title="보내기">
        <div className="utabs">{['공지', '알림장', '설문', '상담'].map((k) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{k}</button>)}</div>
      </SectionHead>
      <Feed key={`${tab}${bump}`} classId={classId} teacher bare first={{ 공지: 'all', 알림장: 'notebook', 설문: 'survey', 상담: 'counsel' }[tab]} />
      <button className="fab" onClick={() => setPlus(true)} aria-label="보내기 만들기"><Ic name="plus" size={26} /></button>
      {plus && (
        <Sheet onClose={() => setPlus(false)}>
          <h3 style={{ textAlign: 'center' }}>무엇을 보낼까요?</h3>
          <div className="ls" style={{ margin: '0 -20px' }}>
            {opts.map(([ic, c, t, go]) => (
              <button key={t} className="li" style={{ padding: '14px 20px' }} onClick={() => { setPlus(false); go() }}>
                <span className={`qic ${c}`}><Ic name={ic} size={20} /></span><div className="g"><b>{t}</b></div></button>))}
          </div>
        </Sheet>
      )}
      {sheet === 'notice' && <NoticeSheet classId={classId} onClose={close} />}
      {sheet === 'notebook' && <NotebookSheet classId={classId} onClose={() => { setTab('알림장'); close() }} />}
      {sheet === 'counsel' && <CounselSheet classId={classId} onClose={() => { setTab('상담'); close() }} />}
      {sheet === 'survey' && <SurveySheet classId={classId} onClose={() => { setTab('설문'); close() }} />}
    </div>
  )
}
