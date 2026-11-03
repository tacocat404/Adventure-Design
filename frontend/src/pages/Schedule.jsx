// 시간표 · 급식 (B-1 직각): 요일 밑줄 탭 → 교시 전폭 줄(지금 교시는 왼쪽 막대) → 점심 급식
import { useState } from 'react'
import { api, usePoll } from '../api.js'
import { Loading } from '../components/ui.jsx'
import { SectionHead } from './TeacherHome.jsx'

const toMin = (hhmm) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m }
const CLASS_MIN = 45 // 한 교시 길이

export default function Schedule({ classId }) {
  const [d, setD] = useState(null)
  const [sel, setSel] = useState(null)
  usePoll(async () => setD(await api(`/classes/${classId}/timetable`)), [classId], 60000)
  const day = d && (d.days.find((x) => x.date === (sel ?? d.today)) || d.days[0])
  const isToday = day && day.date === d.today
  const nowMin = new Date().getHours() * 60 + new Date().getMinutes()

  return (
    <div className="app">
      <SectionHead title="시간표 · 급식">
        {d && <div className="dtabs">{d.days.map((x) => (
          <button key={x.date} className={x.date === day.date ? 'on' : ''} onClick={() => setSel(x.date)}>{x.weekday}<small>{Number(x.date.slice(8))}</small></button>))}</div>}
      </SectionHead>
      <div className="page tight" style={{ paddingTop: 8 }}>
        {!d ? <Loading /> : (
          <>
            <div className="srows">
              {day.periods.map((p) => {
                const start = toMin(p.start)
                const state = !isToday ? '' : nowMin >= start + CLASS_MIN ? 'past' : nowMin >= start ? 'now' : ''
                return (
                  <div key={p.no} className={`srow ${state}`}>
                    <span className="no">{p.no}</span><b>{p.subject}</b>{state === 'now' && <span className="nowtag">지금</span>}<span className="tm">{p.start}</span>
                  </div>
                )
              })}
            </div>
            <div className="band"><span>점심 급식</span><span>{day.lunch}</span></div>
            <div className="meals">{day.meal.map((m) => <span key={m}>{m}</span>)}</div>
          </>
        )}
      </div>
    </div>
  )
}
