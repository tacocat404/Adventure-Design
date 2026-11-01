// C1~C3 메시지함 · C4~C8 상세 · C5 원문 시트 · 탭(메시지함 · 반 톡방 · 설정)
import { useEffect, useState } from 'react'
import { api, usePoll, useUnread, CASE, TYPES, URGENT, dday, dueText, when } from '../api.js'
import { Btn, Composer, Cushi, Filters, Header, Marked, Sheet, Sticker, TabBar, Title } from '../components/ui.jsx'
import { TeacherRooms } from './Rooms.jsx'

export default function Teacher({ me, onOut }) {
  const [tab, setTab] = useState('메시지함')
  const [open, setOpen] = useState(null)
  const [unread, clearUnread] = useUnread()
  if (open) return <Detail id={open} onBack={() => setOpen(null)} />
  return (
    <>
      {tab === '메시지함' && <Inbox onOpen={setOpen} onSeen={clearUnread} />}
      {tab === '반 톡방' && <TeacherRooms me={me} />}
      {tab === '설정' && (
        <div className="app"><Title title="설정" side={me.name} />
          <div className="page"><Btn kind="white" onClick={onOut}>로그아웃</Btn></div></div>
      )}
      <TabBar tabs={['메시지함', '반 톡방', '설정']} on={tab} onPick={setTab} badges={{ 메시지함: tab === '메시지함' ? 0 : unread }} />
    </>
  )
}

const today = () => new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })

function Inbox({ onOpen, onSeen }) {
  const [filter, setFilter] = useState('todo')
  const [d, setD] = useState(null)
  usePoll(async () => { setD(await api(`/teacher/inbox?filter=${filter}`)); onSeen() }, [filter]) // 메시지함을 보고 있으면 알림은 읽은 것
  if (!d) return <div className="app" />
  const empty = !d.urgent.length && !d.items.length
  return (
    <div className="app">
      <Title title="쿠션톡" side={today()} />
      <div className="page">
        {d.masked_since_last_visit > 0 && !empty && (
          <div className="cxr"><Cushi face="safe" size={78} label="막았어요 표정의 쿠션이" />
            <div className="say">밤사이 거친 말 <span className="jua" style={{ color: 'var(--butter-deep)', fontSize: 18 }}>{d.masked_since_last_visit}</span>개를 폭신하게 막아 뒀어요!</div></div>
        )}
        <Filters on={filter} onPick={setFilter} items={[['todo', '답장할 것', d.counts.todo], ['notice', '알림', d.counts.notice], ['school', '학교', d.counts.school]]} />
        {d.urgent.map((u) => (
          <button key={u.id} className="chunk urgent" onClick={() => onOpen(u.id)}>
            <div className="nm"><span className="tag tg-coral">긴급 · {URGENT[u.urgent_type]}</span><span className="t">{when(u.received_at)}</span></div>
            <p style={{ marginTop: 6, fontWeight: 800 }}>{u.child_name} 보호자 <span className="cap" style={{ color: 'var(--coral-deep)' }}>원문 그대로</span></p>
            <p className="sum">{u.preview}…</p>
          </button>
        ))}
        {empty && <div className="empty"><Cushi face="rest" size={96} label="쉬는 중인 쿠션이" /><b>새 연락이 없어요</b><p className="cap">쿠션이도 잠깐 쉬고 있어요. 연락이 오면 먼저 읽고 알려 드릴게요.</p></div>}
        {d.items.length > 0 && <p className="sec">{{ todo: '답장할 것', notice: '알림', school: '학교가 맡은 일' }[filter]}</p>}
        {d.items.map((m) => <Card key={m.id} m={m} onClick={() => onOpen(m.id)} />)}
      </div>
    </div>
  )
}

function Card({ m, onClick }) {
  const due = dday(m.due_date)
  const name = <>{m.child_name} 보호자{m.label && ` · ${m.label}`}</>
  if (m.analysis_status !== 'done') {
    return (
      <button className="chunk failed" onClick={onClick}>
        <div className="nm">{name}<span className="t">{when(m.received_at)}</span></div>
        <p className="sum cap">{m.analysis_status === 'failed' ? 'AI가 읽지 못했어요 · 원문은 접혀 있어요' : '쿠션이가 읽는 중이에요…'}</p>
      </button>
    )
  }
  return (
    <button className={`chunk${m.category === 'threat' ? ' threat' : ''}`} onClick={onClick}>
      <div className="nm">{name}{due && <span className="tag tg-due">{due}</span>}<span className="t">{when(m.received_at)}</span></div>
      <p className="sum">{m.summary}</p>
      <div className="tags">
        {m.category === 'threat' && <span className="tag tg-slate">{CASE[m.case_status]}</span>}
        <span className="tag tg-line">{TYPES[m.msg_type]}</span>
        {m.masked_count > 0 && <Sticker plain={m.category === 'threat'}>{m.masked_count}곳 막음</Sticker>}
      </div>
    </button>
  )
}

function Detail({ id, onBack }) {
  const [d, setD] = useState(null)
  const [orig, setOrig] = useState(null) // { via, text, spans, at }
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const load = async () => setD(await api(`/teacher/messages/${id}`))
  useEffect(() => { load() }, [id]) // 다시 묻지 않음: 긴급 상세는 열 때마다 열람 기록이 남음
  if (!d) return <div className="app" />
  const original = async (via) => {
    const r = await api(`/teacher/messages/${id}/original`, { method: 'POST', body: { via } })
    setOrig({ via, text: r.original_text, spans: r.rough_spans, at: r.received_at })
  }
  const reply = async () => {
    setBusy(true)
    try { await api(`/teacher/messages/${id}/replies`, { method: 'POST', body: { body } }); setBody(''); await load() } finally { setBusy(false) }
  }
  const due = dday(d.due_date)
  const threat = d.category === 'threat'
  const segs = d.segments?.map((s, i) => s.mask ? <Sticker key={i} n={threat ? null : s.mask} plain={threat}>{threat && '가림'}</Sticker> : <span key={i}>{s.t}</span>)

  return (
    <div className="app">
      <Header onBack={onBack} avatar={d.child_name?.[0]} title={`${d.child_name} 보호자`} sub={`${d.grade}학년 ${d.class_no}반 · ${when(d.received_at)}`}
        right={due && <span className="tag tg-due">{due}</span>} />
      <div className="page tight">
        {d.category === 'urgent' && <>
          <div className="banner urgent"><b>긴급 · {URGENT[d.urgent_type] || ''} — 원문 그대로 보여 드려요</b>학교폭력 · 아동학대 · 안전 메시지는 AI가 고치거나 가리지 않아요.</div>
          <span className="chipc">원래 보낸 말</span>
          <div className="bub full">{d.original_text}</div>
        </>}

        {d.analysis_status === 'failed' && <>
          <div className="chunk failed"><b>AI가 이 메시지를 읽지 못했어요</b><p className="cap">거친 표현이 있을 수 있어서 원문은 접어 두었어요.</p></div>
          {orig ? <div className="bub full">{orig.text}</div> : <Btn kind="white" onClick={() => original('failed_expand')}>원문 펼치기 ▾</Btn>}
        </>}
        {d.analysis_status === 'pending' && <div className="cxr"><Cushi face="read" size={48} /><div className="say">쿠션이가 읽는 중이에요. 잠시만요!</div></div>}

        {d.segments && !threat && <>
          <div className="cxr"><Cushi face="read" size={58} label="읽는 중인 쿠션이" />
            <div className="say butter"><p className="lb">쿠션이가 읽어 봤어요</p><p>{d.summary}</p>
              <div className="minis"><div className="mini"><p>기한</p><p>{dueText(d.due_date)}</p></div><div className="mini"><p>유형</p><p>{TYPES[d.msg_type]}</p></div></div></div></div>
        </>}
        {threat && <>
          <div className="banner school"><b>학교로 넘겼어요</b>{CASE[d.case?.status]}</div>
          <div className="chunk"><p className="cap">요약</p><p>{d.summary}</p></div>
        </>}
        {d.segments && <>
          <span className="chipc">원래 보낸 말</span>
          <div className="bub full">{segs}</div>
          {d.masked_count > 0 && <div className="row"><span className="cap grow">거친 표현 {d.masked_count}곳에 {threat ? '가림 표시를' : '스티커를'} 붙였어요</span>
            <button className="btn b-white sm" onClick={() => original('teacher_sheet')}>{threat ? '원문 보기' : '떼고 보기'}</button></div>}
        </>}

        {d.replies.map((r) => <div key={r.id} className="bub me">{r.body}<div className="cap">{when(r.sent_at)}</div></div>)}
      </div>
      <Composer placeholder="답장을 적어 주세요" value={body} onChange={setBody} onSend={reply} busy={busy} />

      {orig?.via === 'teacher_sheet' && (
        <Sheet onClose={() => setOrig(null)}>
          <h3>원문</h3>
          <p className="cap center">{when(orig.at)} 받음 · 거친 표현이 들어 있어요</p>
          <div className="quote"><Marked text={orig.text} spans={orig.spans} /></div>
          <p className="cap center">학부모의 요청은 위 요약에 빠짐없이 담겨 있어요.</p>
          <Btn kind="white" onClick={() => setOrig(null)}>닫기</Btn>
        </Sheet>
      )}
    </div>
  )
}
