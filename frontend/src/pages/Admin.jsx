// 관리자(교감 · 민원대응팀): 위협 대응과 가입 승인만. 하단바 = 위협 · 가입 승인, 위쪽 탭 = 새 알림 · 처리 완료
// 교사 · 학부모 화면과 같은 구조(구역 머리글, 납작한 목록, 사각 하단 바). 관리자 화면에는 쿠션이가 없다.
import { useEffect, useState } from 'react'
import { api, usePoll, ACTIONS, CASE, when } from '../api.js'
import { Chip, Header, Ic, Loading, Marked, TabBar } from '../components/ui.jsx'
import { AccountSheet, MenuCtx, SectionHead } from './TeacherHome.jsx'

const PROVIDER = { kakao: '카카오', google: '구글' }

export default function Admin({ me, onOut }) {
  const [tab, setTab] = useState('위협')
  const [sub, setSub] = useState('new')
  const [d, setD] = useState(null)
  const [pending, setPending] = useState([])
  const [open, setOpen] = useState(null) // 위협 건
  const [menu, setMenu] = useState(false)
  const [toast, setToast] = useState(null)
  const load = async () => {
    setD(await api(`/admin/cases?status=${sub}`))
    setPending((await api('/admin/members')).pending)
  }
  usePoll(load, [sub])
  const note = (msg) => { setToast(msg); setTimeout(() => setToast(null), 2200) }
  const decide = async (m, ok) => {
    await api(`/admin/members/${m.id}/${ok ? 'approve' : 'reject'}`, { method: 'POST' })
    note(ok ? '승인했어요' : '거절했어요'); load()
  }
  if (open) return <CaseDetail item={open} onBack={() => setOpen(null)} onDone={(msg) => { setOpen(null); note(msg); load() }} />
  const newCount = d?.counts.new ?? 0

  return (
    <MenuCtx.Provider value={() => setMenu(true)}>
      {tab === '위협' && (
        <div className="app">
          <SectionHead title="위협" mascot={false}>
            <div className="utabs">
              <button className={sub === 'new' ? 'on' : ''} onClick={() => setSub('new')}><span className="lbl">새 알림{newCount > 0 && <i className="rb">{newCount}</i>}</span></button>
              <button className={sub === 'handled' ? 'on' : ''} onClick={() => setSub('handled')}>처리 완료</button>
            </div>
          </SectionHead>
          <div className="page tight" style={{ paddingTop: 6 }}>
            {!d ? <Loading /> : d.cases.length === 0
              ? <div className="empty"><span className="ring"><Ic name="check" size={32} /></span><b>{sub === 'new' ? '새 알림 없음' : '처리한 알림 없음'}</b></div>
              : <div className="ls">{d.cases.map((k) => (
                  <button key={k.id} className="li" onClick={() => setOpen(k)}>
                    <div className="g">
                      <div className="rowc"><b>{k.grade}학년 {k.class_no}반</b><Chip kind="slate">{sub === 'new' ? '새 알림' : CASE[k.status]}</Chip><span className="t">{when(k.opened_at)}</span></div>
                      <p>{k.child_name} 보호자 → {k.teacher_name} 선생님 · {k.label}{k.last_action ? ` · ${ACTIONS[k.last_action.action_type]}` : ''}</p>
                    </div><span className="go">›</span>
                  </button>))}</div>}
          </div>
        </div>
      )}
      {tab === '가입 승인' && (
        <div className="app">
          <SectionHead title="가입 승인" mascot={false} />
          <div className="page tight" style={{ paddingTop: 6 }}>
            {pending.length === 0
              ? <div className="empty"><span className="ring"><Ic name="check" size={32} /></span><b>대기 없음</b></div>
              : <div className="ls">{pending.map((m) => (
                  <div key={m.id} className="li">
                    <div className="g"><div className="rowc"><b>{m.name}</b><Chip kind="sky">{m.role === 'admin' ? '교감 · 민원대응팀' : '담임'}</Chip></div>
                      <p>{PROVIDER[m.provider] || '아이디'} · {when(m.created_at)}</p></div>
                    <button className="btn b-white sm flat" onClick={() => decide(m, false)}>거절</button>
                    <button className="btn b-sky sm flat" onClick={() => decide(m, true)}>승인</button>
                  </div>))}</div>}
          </div>
        </div>
      )}
      <TabBar tabs={['위협', '가입 승인']} on={tab} onPick={setTab} badges={{ 위협: newCount, '가입 승인': pending.length }} alerts={{ 위협: newCount > 0 }} />
      {menu && <AccountSheet me={me} sub={me.school_name} onClose={() => setMenu(false)} onOut={onOut} />}
      {toast && <div className="toast" role="status">{toast}</div>}
    </MenuCtx.Provider>
  )
}

// 위협 한 건: 원문과 근거를 한 화면에, 조치는 하단 바에서
function CaseDetail({ item, onBack, onDone }) {
  const [k, setK] = useState(null)
  const [act, setAct] = useState('meeting')
  const [memo, setMemo] = useState('')
  const [sure, setSure] = useState(false) // 일반 메시지로 되돌리기는 두 번 눌러야 한다
  const [err, setErr] = useState(null)
  useEffect(() => { api(`/admin/cases/${item.id}`).then(setK) }, [item.id]) // 한 번만: 열 때마다 열람 기록이 남음
  if (!k) return <div className="app"><Header onBack={onBack} title="위협" /><Loading /></div>
  const closed = k.status === 'returned'
  const run = async (path, body, msg) => {
    try { await api(`/admin/cases/${item.id}/${path}`, { method: 'POST', body }); onDone(msg) } catch (e) { setErr(e.message) }
  }
  const kv = (a, b) => <div className="kv2"><span style={{ width: 70 }}>{a}</span><b>{b}</b></div>
  return (
    <div className="app">
      <Header onBack={onBack} title={`${item.grade}학년 ${item.class_no}반`} sub={`${item.child_name} 보호자 → ${item.teacher_name} 선생님`} right={<Chip kind="slate">{CASE[k.status] || '새 알림'}</Chip>} />
      <div className="page tight" style={{ paddingBottom: closed ? 24 : 110 }}>
        <div className="ls">
          {kv('받은 시간', new Date(k.received_at).toLocaleString('ko-KR'))}
          {kv('판단 이유', k.threat_reason)}
          {kv('원문 무결성', k.hash_ok ? '변경 없음' : '지문 불일치')}
        </div>
        <div className="band"><span>원문</span></div>
        <div className="quote" style={{ borderRadius: 0, margin: '0 -16px' }}><Marked text={k.original_text} spans={k.rough_spans} /></div>
        {k.actions.length > 0 && <>
          <div className="band"><span>대응 이력</span><span>{k.actions.length}</span></div>
          <div className="ls">{k.actions.map((a) => (
            <div key={a.id} className="li"><div className="g"><b>{ACTIONS[a.action_type]}</b><p>{when(a.created_at)} · {a.admin_name}{a.memo ? ` · ${a.memo}` : ''}</p></div></div>))}</div>
        </>}
        {!closed && <>
          <div className="band"><span>조치</span></div>
          <div className="ls">{['meeting', 'report_office', 'report_police', 'other'].map((t) => (
            <button key={t} className="li" role="radio" aria-checked={act === t} onClick={() => setAct(t)}>
              <div className="g"><b>{ACTIONS[t]}</b></div>{act === t && <span className="ok"><Ic name="check" size={18} /></span>}</button>))}</div>
          <textarea className="rowarea" value={memo} maxLength={1000} onChange={(e) => setMemo(e.target.value)} placeholder="조치 내용" aria-label="조치 내용" />
        </>}
        {err && <p className="err" role="alert">{err}</p>}
      </div>
      {!closed && (
        <div className="bar2">
          <button onClick={() => (sure ? run('return', { memo: memo || null }, '일반 메시지로 되돌렸어요') : setSure(true))} style={sure ? { color: 'var(--coral-deep)' } : undefined}>{sure ? '되돌리기 확인' : '일반으로 되돌리기'}</button>
          <button className="p" onClick={() => run('actions', { action_type: act, memo: memo || null }, '기록했어요')}>기록 저장</button>
        </div>
      )}
    </div>
  )
}
