// 학생: 참여 코드로 들어온 반의 홈 — 학부모와 같은 4분면 (반 톡방 · 알림장 · 학교소식 · 시간표·급식), 읽기 전용
import { useState } from 'react'
import { api, usePoll } from '../api.js'
import { ClassHead, Cushi, Ic, TabBar } from '../components/ui.jsx'
import { Feed } from './School.jsx'
import Schedule from './Schedule.jsx'
import { TodayNotebook } from './Care.jsx'
import { StudentTalk } from './Rooms.jsx'
import { AccountSheet, MenuCtx, SectionHead } from './TeacherHome.jsx'

// 성을 떼고 이름만 부른다: 받침이 있으면 "서준이", 없으면 "지호". 두 글자 이름은 그대로.
const callName = (full) => {
  const n = full.length >= 3 ? full.slice(1) : full
  const c = n.charCodeAt(n.length - 1)
  const hasBatchim = c >= 0xAC00 && c <= 0xD7A3 && (c - 0xAC00) % 28 !== 0
  return hasBatchim ? `${n}이` : n
}

export default function Student({ me, classId, onOut }) {
  const [tab, setTab] = useState('홈')
  const [first, setFirst] = useState('all')
  const [menu, setMenu] = useState(false)
  const [talkInit, setTalkInit] = useState(null) // 톡방 탭을 열 때 바로 열 곳
  const [chat, setChat] = useState(false) // 채팅 중엔 하단바를 숨김
  const [info, setInfo] = useState(null)
  const [d, setD] = useState(null)
  usePoll(async () => { setInfo(await api(`/rooms/${classId}/messages`)); setD(await api(`/classes/${classId}/today`)) }, [classId], 15000)
  const m = info?.class_name?.match(/(\d+)학년 (\d+)반/)
  const go = (to) => {
    if (to === '알림장') { setFirst('notebook'); return setTab('소식') }
    if (to === '반 톡방') { setTalkInit('room'); return setTab('톡방') }
    setFirst('all'); setTab(to)
  }
  return (
    <MenuCtx.Provider value={() => setMenu(true)}>
      {tab === '홈' && (
        <div className="app">
          <SectionHead title="쿠션톡">
            {m && <ClassHead grade={m[1]} classNo={m[2]} sub={`${me.school_name || ''} · ${me.name}`} icon="반 톡방" label="톡방" onAct={() => go('반 톡방')} />}
          </SectionHead>
          <div className="page" style={{ paddingTop: 6 }}>
            <div className="cxr"><Cushi face="hi" size={64} /><div className="say">{callName(me.name)} 안녕~~</div></div>
            <div className="quick">
              <button onClick={() => go('반 톡방')}><span className="qic s"><Ic name="반 톡방" /></span>반 톡방</button>
              <button onClick={() => go('알림장')}><span className="qic b"><Ic name="양식" /></span>알림장</button>
              <button onClick={() => go('소식')}><span className="qic m"><Ic name="소식" /></span>학교소식</button>
              <button onClick={() => go('시간표')}><span className="qic c"><Ic name="상담" /></span>시간표 · 급식</button>
            </div>
            <TodayNotebook classId={classId} readonly />
            {d && <>
              <p className="sec">오늘</p>
              <div className="chunk">
                <div className="row"><b>{new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'long' })}</b></div>
                <div style={{ marginTop: 6 }}>{d.timetable.map((s, i) => <div className="tt-row" key={i}><i>{i + 1}</i>{s}</div>)}</div>
              </div>
            </>}
          </div>
        </div>
      )}
      {tab === '톡방' && <StudentTalk key={talkInit || 'list'} me={me} classId={classId} initial={talkInit} onChat={setChat} />}
      {tab === '시간표' && <Schedule classId={classId} />}
      {tab === '소식' && <Feed key={first} classId={classId} first={first} student />}
      {!(tab === '톡방' && chat) && <TabBar tabs={['홈', '톡방', '시간표', '소식']} on={tab} onPick={(t) => { setFirst('all'); setTalkInit(null); setTab(t) }} />}
      {menu && <AccountSheet me={me} sub={info?.class_name || me.school_name} onClose={() => setMenu(false)} onOut={onOut} />}
    </MenuCtx.Provider>
  )
}
