// 교사: 홈(카테고리 바) · 메시지 상세 C4~C8 · 원문 시트 C5 · 보내기(공지 · 설문 · 반 톡방) · 설정
import { useEffect, useState } from 'react'
import { api, usePoll, useUnread, CASE, TYPES, URGENT, when } from '../api.js'
import { Btn, Composer, Cushi, CushionNote, Header, Marked, Sheet, Sticker, TabBar, Title } from '../components/ui.jsx'
import { AccountSheet, Approvals, Attendance, AlarmCtx, MenuCtx, Messages, TripDetail, tabSignals, useAlarm, useTeacherHome } from './TeacherHome.jsx'
import { JoinCodeSheet, TeacherTalk } from './Rooms.jsx'
import { Send, useTeacherClass } from './School.jsx'

// 하단바 = 큰 구역. 위쪽 탭은 구역 안의 갈래만 (메시지: 답장할 것/학교가 맡은 일 · 보내기: 공지/설문/반 톡방)
export default function Teacher({ me, onOut }) {
  const [tab, setTab] = useState('메시지')
  const [open, setOpen] = useState(null) // 메시지 id
  const [trip, setTrip] = useState(null) // 체험학습 신청서
  const [sendTab, setSendTab] = useState('공지')
  const [chat, setChat] = useState(false) // 반 톡방 채팅 중
  const [talk, setTalk] = useState(null) // 메시지 상세에서 톡방으로 넘어갈 학부모
  const [menu, setMenu] = useState(null) // account · code
  const [, clearUnread] = useUnread()
  const room = useTeacherClass()
  const classId = room?.class_id
  const [d, reload] = useTeacherHome(classId)
  const [req, setReq] = useState(null) // 홈에서 바로 열 시트 (알림장 쓰기)
  const alarm = useAlarm()
  const { badges, alerts } = tabSignals(d, alarm.off)
  if (open) return <Detail id={open} onBack={() => { setOpen(null); reload() }} onTalk={(parent, title) => { setTalk({ parent, title }); setOpen(null); setTab('톡방'); reload() }} />
  if (trip) return <TripDetail trip={trip} onBack={() => { setTrip(null); reload() }} />
  return (
    <MenuCtx.Provider value={() => setMenu('account')}>
      <AlarmCtx.Provider value={alarm.off}>
      {tab === '메시지' && <Messages me={me} room={room} d={d} alarm={alarm} clearUnread={clearUnread} onOpen={setOpen} reload={reload} onRoom={() => setTab('톡방')} onGo={(to, sheet) => { setSendTab(to); setReq(sheet || null); setTab('보내기') }} />}
      {tab === '출결' && <Attendance d={d} reload={reload} />}
      {tab === '승인' && <Approvals d={d} onTrip={setTrip} />}
      {tab === '톡방' && <TeacherTalk key={talk?.parent || 'list'} me={me} classId={classId} initial={talk} onChat={setChat} />}
      {tab === '보내기' && <Send me={me} classId={classId} tab={sendTab} setTab={setSendTab} initialSheet={req} />}
      {!(tab === '톡방' && chat) && <TabBar tabs={['메시지', '출결', '승인', '톡방', '보내기']} on={tab} onPick={(t) => { setTalk(null); setReq(null); setTab(t) }} badges={badges} alerts={alerts} />}
      {menu === 'account' && <AccountSheet me={me} room={room} onClose={() => setMenu(null)} onCode={() => setMenu('code')} onOut={onOut} />}
      {menu === 'code' && <JoinCodeSheet classId={classId} name={`${room.grade}학년 ${room.class_no}반`} onClose={() => setMenu(null)} />}
      </AlarmCtx.Provider>
    </MenuCtx.Provider>
  )
}

function Detail({ id, onBack, onTalk }) {
  const [d, setD] = useState(null)
  const [orig, setOrig] = useState(null) // { via, text, spans, at }
  const load = async () => setD(await api(`/teacher/messages/${id}`))
  useEffect(() => { load() }, [id]) // 다시 묻지 않음: 긴급 상세는 열 때마다 열람 기록이 남음
  if (!d) return <div className="app" />
  const original = async (via, show = via) => {
    const r = await api(`/teacher/messages/${id}/original`, { method: 'POST', body: { via } })
    setOrig({ via: show, text: r.original_text, spans: r.rough_spans, at: r.received_at })
  }
  const segs = d.segments?.map((s, i) => s.mask ? <Sticker key={i} n={s.mask} /> : <span key={i}>{s.t}</span>)

  return (
    <div className="app">
      <Header onBack={onBack} avatar={d.child_name?.[0]} title={`${d.child_name} 보호자`} sub={`${d.grade}학년 ${d.class_no}반 · ${when(d.received_at)}`} />
      <div className="page tight">
        {d.category === 'urgent' && <>
          <div className="banner urgent"><b>긴급 · {URGENT[d.urgent_type] || ''}</b></div>
          <span className="chipc">원래 보낸 말</span>
          <div className="bub full">{d.original_text}</div>
        </>}

        {d.analysis_status === 'failed' && <>
          <div className="chunk failed"><b>분석 실패</b></div>
          {orig ? <div className="bub full">{orig.text}</div> : <Btn kind="white" onClick={() => original('failed_expand')}>원문 펼치기 ▾</Btn>}
        </>}
        {d.analysis_status === 'pending' && <p className="cap center">분석 중</p>}

        {d.cushion && <>
          <CushionNote summary={d.summary} type={TYPES[d.msg_type]} original={orig?.text} open={orig?.via === 'cushion'}
            onToggle={() => (orig?.via === 'cushion' ? setOrig(null) : original('teacher_sheet', 'cushion'))} />
          {d.case && <div className="banner school"><b>학교 이관</b>{CASE[d.case.status]}</div>}
        </>}
        {/* 위협도 일반과 같은 화면: 걸러 낸 원문 + 요약 + 기한 · 유형 (11.03 팀장 결정, E2의 “위협 화면엔 쿠션이 없음”을 바꿈) */}
        {d.segments && <>
          <div className="cxr"><Cushi face="read" size={58} label="읽는 중인 쿠션이" />
            <div className="say butter"><p className="lb">요약</p><p>{d.summary}</p>
              <div className="minis"><div className="mini"><p>유형</p><p>{TYPES[d.msg_type]}</p></div></div></div></div>
        </>}
        {d.segments && <>
          <span className="chipc">원래 보낸 말</span>
          <div className="bub full">{segs}</div>
          {d.masked_count > 0 && <div className="row"><span className="cap grow">{d.masked_count}곳 가림</span>
            <button className="btn b-white sm" onClick={() => original('teacher_sheet')}>원문 보기</button></div>}
        </>}

      </div>
      <div className="dock"><Btn onClick={() => onTalk(d.parent_id, `${d.child_name} 보호자`)}>톡방에서 답장</Btn></div>

      {orig?.via === 'teacher_sheet' && (
        <Sheet onClose={() => setOrig(null)}>
          <h3>원문</h3>
          <p className="cap center">{when(orig.at)} 받음</p>
          <div className="quote"><Marked text={orig.text} spans={orig.spans} /></div>
          <Btn kind="white" onClick={() => setOrig(null)}>닫기</Btn>
        </Sheet>
      )}
    </div>
  )
}
