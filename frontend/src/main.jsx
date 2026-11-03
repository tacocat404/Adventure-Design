// 앱 시작: 저장된 토큰 확인(G-4) → 역할별 첫 화면
import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { api, auth } from './api.js'
import Login from './pages/Login.jsx'
import Parent from './pages/Parent.jsx'
import Teacher from './pages/Teacher.jsx'
import Admin from './pages/Admin.jsx'
import Student from './pages/Student.jsx'
import './styles.css'
import './melt.css'

function App() {
  const [me, setMe] = useState(null)
  const [ready, setReady] = useState(!auth.token)
  useEffect(() => {
    if (auth.token) api('/me').then((r) => setMe(r.user)).catch(() => auth.clear()).finally(() => setReady(true))
  }, [])
  const signIn = (r) => { auth.set(r.token, r.class_id); setMe(r.user) }
  const signOut = async () => { await api('/auth/logout', { method: 'POST' }).catch(() => {}); auth.clear(); setMe(null) }

  if (!ready) return null
  if (!me) return <Login onIn={signIn} />
  if (me.role === 'student') return <Student me={me} classId={auth.classId} onOut={signOut} />
  const Page = { parent: Parent, teacher: Teacher, admin: Admin }[me.role]
  return <Page me={me} onOut={signOut} />
}

createRoot(document.getElementById('root')).render(<App />)
