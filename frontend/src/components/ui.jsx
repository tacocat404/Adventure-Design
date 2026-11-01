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

export const Dot = ({ n }) => n > 0 ? <span className="dot" aria-label={`새 알림 ${n}개`}>{n > 99 ? '99+' : n}</span> : null

export const TabBar = ({ tabs, on, onPick, badges = {} }) => (
  <nav className="tabbar">
    {tabs.map((t) => <button key={t} className={`tab${on === t ? ' on' : ''}`} onClick={() => onPick(t)}>{t}<Dot n={badges[t]} /></button>)}
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
