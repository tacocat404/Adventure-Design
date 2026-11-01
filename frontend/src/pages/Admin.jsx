// D1 위협 알림 · D2 위협 상세 · 대응 기록 · D3 처리 완료 — 관리자 화면에는 쿠션이 없음
import { useEffect, useState } from 'react'
import { api, usePoll, ACTIONS, CASE, when } from '../api.js'
import { Btn, Filters, Marked, Sheet, Title } from '../components/ui.jsx'

export default function Admin({ onOut }) {
  const [status, setStatus] = useState('new')
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(null)
  const [toast, setToast] = useState(null)
  const load = async () => setD(await api(`/admin/cases?status=${status}`))
  usePoll(load, [status])
  const done = (msg) => { setOpen(null); setToast(msg); setTimeout(() => setToast(null), 2500); load() }
  return (
    <div className="app">
      <Title title="위협 알림" side="교감 · 민원대응팀" right={<button className="cap" onClick={onOut}>로그아웃</button>} />
      <div className="page tight">
        {d && <Filters on={status} onPick={setStatus} items={[['new', '새 알림', d.counts.new], ['handled', '처리 완료', d.counts.handled]]} />}
        {d?.cases.length === 0 && <p className="cap center" style={{ padding: 40 }}>{status === 'new' ? '새 위협 알림이 없어요.' : '처리한 알림이 없어요.'}</p>}
        {d?.cases.map((k) => (
          <button key={k.id} className="chunk threat" onClick={() => setOpen(k.id)}>
            <div className="nm">위협 감지<span className="t">{when(k.opened_at)}</span></div>
            <p className="sum">{k.grade}학년 {k.class_no}반 담임에게 온 메시지에서 위협 표현이 감지됐어요</p>
            <p className="cap">{k.child_name} 보호자 → {k.grade}학년 {k.class_no}반 담임 {k.teacher_name}</p>
            <div className="tags"><span className="tag tg-slate">{status === 'new' ? '새 알림' : CASE[k.status]}</span><span className="tag tg-line">{k.label}</span>
              {k.last_action && <span className="tag tg-line">{ACTIONS[k.last_action.action_type]} · {when(k.last_action.created_at)}</span>}</div>
          </button>
        ))}
      </div>
      {open && <CaseSheet id={open} onClose={() => setOpen(null)} onDone={done} />}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  )
}

function CaseSheet({ id, onClose, onDone }) {
  const [k, setK] = useState(null)
  const [act, setAct] = useState('meeting')
  const [memo, setMemo] = useState('')
  const [err, setErr] = useState(null)
  useEffect(() => { api(`/admin/cases/${id}`).then(setK) }, [id]) // 한 번만: 열 때마다 열람 기록이 남음
  if (!k) return null
  const run = async (path, body, msg) => {
    try { await api(`/admin/cases/${id}/${path}`, { method: 'POST', body }); onDone(msg) } catch (e) { setErr(e.message) }
  }
  return (
    <Sheet onClose={onClose}>
      <h3>위협 메시지</h3>
      <p className="lbl">원문 · 고칠 수 없게 보존됨</p>
      <div className="quote"><Marked text={k.original_text} spans={k.rough_spans} /></div>
      <dl className="kv">
        <dt>받은 시간</dt><dd>{new Date(k.received_at).toLocaleString('ko-KR')}</dd>
        <dt>원문 지문</dt><dd>{k.hash_ok ? '✓ 받은 뒤 바뀌지 않았어요' : '⚠ 지문이 맞지 않아요'}</dd>
        <dt>위협으로 본 이유</dt><dd>{k.threat_reason}</dd>
      </dl>
      {k.actions.length > 0 && <>
        <p className="lbl">지난 기록</p>
        {k.actions.map((a) => <p key={a.id} className="cap">{when(a.created_at)} · {a.admin_name} · {ACTIONS[a.action_type]}{a.memo && ` — ${a.memo}`}</p>)}
      </>}
      {k.status !== 'returned' && <>
        <p className="lbl">대응 기록</p>
        <div className="radios" role="radiogroup">
          {['meeting', 'report_office', 'report_police', 'other'].map((t) => (
            <button key={t} role="radio" aria-checked={act === t} className={act === t ? 'on' : ''} onClick={() => setAct(t)}><span className="radio" />{ACTIONS[t]}</button>
          ))}
        </div>
        <textarea className="field" style={{ height: 80, padding: 12 }} placeholder="어떤 조치를 했는지 적어 주세요" value={memo} onChange={(e) => setMemo(e.target.value)} />
        {err && <p className="err">{err}</p>}
        <Btn kind="slate" onClick={() => run('actions', { action_type: act, memo: memo || null }, '기록했어요. 담임 선생님께 처리 상황을 알렸어요.')}>기록 저장</Btn>
        <button className="btn b-ghost" onClick={() => confirm('일반 메시지로 되돌릴까요? 담임 메시지함으로 돌아가요.') && run('return', { memo: memo || null }, '일반 메시지로 되돌렸어요.')}>일반 메시지로 되돌리기</button>
      </>}
    </Sheet>
  )
}
