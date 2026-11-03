// 공통 부품 — 컴포넌트 명세 21개 중 화면에서 쓰는 것만
export const Cushi = ({ face, size = 58, label }) => (
  <span className="cx">
    <svg width={size} height={Math.round(size * 0.84)} viewBox="0 0 120 100" aria-label={label || `쿠션이 ${face}`}><use href={`#cx-${face}`} /></svg>
  </span>
)

export const Sticker = ({ n, plain, children }) => (
  <span className={`sticker${plain ? ' plain' : ''}`}>
    {!plain && <svg><use href="#cx-face" /></svg>}
    {n ? <i>{n}</i> : children}
  </span>
)

export const Title = ({ title, side, right }) => (
  <div className="ttl"><b>{title}</b><span className="row"><small>{side}</small>{right}</span></div>
)

export const Header = ({ title, sub, onBack, avatar, right }) => (
  <div className="hdr">
    {onBack && <button className="back" onClick={onBack} aria-label="뒤로">‹</button>}
    {avatar && <span className="av">{avatar}</span>}
    <div className="f1"><b>{title}</b>{sub && <small>{sub}</small>}</div>
    {right}
  </div>
)

export const Btn = ({ kind = 'sky', className = '', ...p }) => <button className={`btn b-${kind} ${className}`} {...p} />

export const Sheet = ({ onClose, warn, children }) => (
  <>
    <div className="dim" onClick={onClose} />
    <div className={`sheet${warn ? ' warn' : ''}`} role="dialog">
      {warn ? <div className="sign"><span className="plate">잠깐만요!</span><Cushi face="wait" size={96} /></div> : <span className="handle" />}
      {children}
    </div>
  </>
)

export const Filters = ({ items, on, onPick }) => (
  <div className="filts">
    {items.map(([key, label, n]) => (
      <button key={key} className={`filt f-${key}${on === key ? ' on' : ''}`} onClick={() => onPick(key)}><b>{n}</b>{label}</button>
    ))}
  </div>
)

export const Loading = () => <div className="empty" role="status" aria-label="불러오는 중"><span className="spin dk" /></div>

export const Dot = ({ n }) => n > 0 ? <span className="dot" aria-label={`새 알림 ${n}개`}>{n > 99 ? '99+' : n}</span> : null

// 탭 아이콘 (24×24 선 그림)
const ICON = {
  홈: 'M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  메시지: 'M4 5h16v11H9l-5 4z', 승인: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12.5l3 3 5-6',
  연락: 'M4 5h16v11H9l-5 4z', 메시지함: 'M4 5h16v11H9l-5 4z',
  학교소식: 'M4 5h12v14H6a2 2 0 0 1-2-2zM16 9h4v8a2 2 0 0 1-2 2M8 9h5M8 13h5', 공지: 'M4 5h12v14H6a2 2 0 0 1-2-2zM16 9h4v8a2 2 0 0 1-2 2M8 9h5M8 13h5',
  출결: 'M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM8 12.5l3 3 5-6',
  '반 톡방': 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20c0-3.5 2.7-5.5 6-5.5s6 2 6 5.5M17 10a2.4 2.4 0 1 0 0-4.8M15.5 14.5c3 0 5.5 1.6 5.5 4.8',
  '내 정보': 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4.4 3.6-7 8-7s8 2.6 8 7', 설정: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4.4 3.6-7 8-7s8 2.6 8 7',
  양식: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5',
  상담: 'M3 5h18v16H3zM3 10h18M8 3v4M16 3v4M8 15h3',
  위협: 'M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z', '가입 승인': 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4.4 3.6-7 8-7s8 2.6 8 7',
  시간표: 'M3 5h18v16H3zM3 10h18M8 3v4M16 3v4M8 15h3',
  첨부: 'M21 12.5l-8.5 8.5a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8', 스크랩: 'M12 17.3l-5.4 3 1-6L3.2 9.8l6-.9L12 3.5l2.8 5.4 6 .9-4.4 4.5 1 6z',
  tick: 'M5 12.5l4.5 4.5L19 7',
  메뉴: 'M4 7h16M4 12h16M4 17h16', 하트: 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z', 답장: 'M9 14L4 9l5-5M4 9h11a5 5 0 0 1 5 5v2', 고정: 'M12 17v5M9 3h6l-1 6 3 3H7l3-3z', 펼침: 'M6 9l6 6 6-6',
  톡방: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20c0-3.5 2.7-5.5 6-5.5s6 2 6 5.5M17 10a2.4 2.4 0 1 0 0-4.8M15.5 14.5c3 0 5.5 1.6 5.5 4.8',
  신청: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2M9 5h6M9 12h6M9 16h4',
  소식: 'M4 5h12v14H6a2 2 0 0 1-2-2zM16 9h4v8a2 2 0 0 1-2 2M8 9h5M8 13h5',
  오늘: 'M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM8 12.5l3 3 5-6', 보내기: 'M4 12l16-8-6 16-3-7z',
  shield: 'M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z', check: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM8 12.5l3 3 5-6', plus: 'M12 5v14M5 12h14',
  absent: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM9 9l6 6M15 9l-6 6', early: 'M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4M16 8l4 4-4 4M20 12H9',
  late: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2', news: 'M4 5h12v14H6a2 2 0 0 1-2-2zM16 9h4v8a2 2 0 0 1-2 2M8 9h5M8 13h5', 설문: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 3v9h9',
}
export const Ic = ({ name, size = 22, fill = 'none' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={ICON[name]} /></svg>
)

// 반 머리글: 왼쪽 반 표지 · 반 이름 · 학교, 오른쪽 버튼 하나 (예: 톡방)
export const ClassHead = ({ grade, classNo, sub, icon, label, onAct }) => (
  <div className="chead">
    <span className="badge">{grade}-{classNo}</span>
    <div className="g"><b>{grade}학년 {classNo}반</b><small>{sub}</small></div>
    {onAct && <button className="act" onClick={onAct}><Ic name={icon} size={16} />{label}</button>}
  </div>
)

export const Chip = ({ kind = 'line', children }) => <span className={`tag tg-${kind}`}>{children}</span>

export const TabBar = ({ tabs, on, onPick, badges = {}, alerts = {} }) => (
  <nav className="tabbar">
    {tabs.map((t) => <button key={t} className={`tab${on === t ? ' on' : ''}${alerts[t] ? ' alert' : ''}`} onClick={() => onPick(t)}><Ic name={t} />{t}<Dot n={badges[t]} /></button>)}
  </nav>
)

export function Composer({ placeholder, value, onChange, onSend, busy, children }) {
  return (
    <div className="compose">
      {children}
      <div className="in">
        <textarea rows={1} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} aria-label={placeholder} />
        <button className="send" disabled={busy || !value.trim()} onClick={onSend} aria-label="보내기">{busy ? <span className="spin" /> : '↑'}</button>
      </div>
    </div>
  )
}

// 원문 위 거친 구절에 물결 밑줄
export function Marked({ text, spans = [] }) {
  const out = []
  let last = 0
  spans.forEach((s, i) => {
    out.push(text.slice(last, s.start), <span key={i} className="wiggle">{text.slice(s.start, s.end)}</span>)
    last = s.end
  })
  out.push(text.slice(last))
  return <>{out}</>
}
