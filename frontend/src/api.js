// API 부르기 · 공통 글자 — docs/06_API/API명세_쿠션톡_261102.html
import { useEffect, useState } from 'react'

const store = {
  get: (k) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v) } catch { /* 저장 못 하면 이번만 로그인 */ } },
}
export const auth = {
  get token() { return store.get('cushion_token') },
  get classId() { return Number(store.get('cushion_class')) || null },
  set(token, classId) { store.set('cushion_token', token); store.set('cushion_class', classId ?? null) },
  clear() { store.set('cushion_token', null); store.set('cushion_class', null) },
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = {}
  if (body) headers['Content-Type'] = 'application/json'
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`
  const r = await fetch(`/api${path}`, { method, headers, body: body && JSON.stringify(body) })
  if (r.status === 204) return null
  const data = await r.json().catch(() => ({}))
  if (!r.ok) {
    const code = data.error?.code || 'NETWORK'
    if (code === 'UNAUTHORIZED') { auth.clear(); location.reload() }
    throw Object.assign(new Error(ERR[code] || data.error?.message || '잠시 뒤 다시 해 주세요.'), { code })
  }
  return data
}

// 실시간 연결 대신 10초마다 다시 묻기 (명세 01절)
export function usePoll(fn, deps, ms = 10000) {
  useEffect(() => {
    fn().catch(() => {})
    const t = setInterval(() => fn().catch(() => {}), ms)
    return () => clearInterval(t)
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps
}

// 안 읽은 알림 수(N-1)와 모두 읽음(N-2)
export function useUnread() {
  const [n, setN] = useState(0)
  usePoll(async () => setN((await api('/notifications?unread=1')).unread_count), [])
  const clear = () => api('/notifications/read', { method: 'POST', body: {} }).then(() => setN(0)).catch(() => {})
  return [n, clear]
}

// 명세 04절 오류 코드 → 화면 문구
export const ERR = {
  VALIDATION: '입력한 내용을 다시 확인해 주세요.',
  WRONG_CREDENTIALS: '아이디 또는 비밀번호가 맞지 않아요.',
  FORBIDDEN: '볼 수 없는 내용이에요.',
  NOT_FOUND: '찾을 수 없어요.',
  LOGIN_ID_TAKEN: '이미 쓰고 있는 아이디예요.',
  NOT_LINKED: '선생님 목록에서 먼저 선생님을 골라 주세요.',
  CLASS_TAKEN: '이미 다른 선생님이 연 반이에요.',
  ALREADY_CLOSED: '이미 처리된 알림이에요.',
  CODE_NOT_FOUND: '코드가 맞지 않아요.',
  CODE_EXPIRED: '코드가 만료됐어요. 선생님께 새 코드를 받아 주세요.',
}

export const TYPES = { counsel: '상담', absence: '결석·조퇴', seating: '자리·모둠', study: '학습', life: '생활', other: '기타' }
export const URGENT = { school_violence: '학교폭력', child_abuse: '아동학대', safety: '안전' }
export const ACTIONS = { meeting: '학부모 면담', report_office: '교육청 보고', report_police: '수사기관 신고', other: '기타', return_normal: '일반 메시지로 되돌림' }
export const CASE = { new: '교감 선생님이 확인 중', handled: '처리 완료', returned: '일반 메시지로 되돌림' }

export function when(iso) {
  if (!iso) return ''
  const d = new Date(iso), today = new Date()
  const days = Math.round((new Date(today.toDateString()) - new Date(d.toDateString())) / 864e5)
  const time = d.toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' })
  return days === 0 ? `오늘 ${time}` : days === 1 ? `어제 ${time}` : d.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })
}

export function dday(due) {
  if (!due) return null
  const n = Math.round((new Date(due) - new Date(new Date().toDateString())) / 864e5)
  return n === 0 ? '오늘' : n > 0 ? `D-${n}` : '기한 지남'
}

export const dueText = (due) => due ? new Date(due).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' }) : '정하지 않음'
