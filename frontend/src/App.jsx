import { useEffect, useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { fetchMe, logoutUser } from './api/auth-api.js'
import NavBar from './components/NavBar.jsx'
import AuthPage from './pages/AuthPage.jsx'

function App() {
  const [user, setUser] = useState(null)
  const [authChecked, setAuthChecked] = useState(false)

  const refreshUser = async () => {
    const me = await fetchMe()
    setUser(me)
    setAuthChecked(true)
  }

  const handleLogout = async () => {
    await logoutUser()
    await refreshUser()
  }

  useEffect(() => {
    refreshUser()
  }, [])

  if (!authChecked) return <p>Loading...</p>

  return (
    <>
      <NavBar user={user} onLogout={handleLogout} />
      <main>
        <Routes>
          <Route path="/" element={<h1>Tiny Paywall</h1>} />
          <Route path="/login" element={<AuthPage onAuthed={refreshUser} />} />
        </Routes>
      </main>
    </>
  )
}

export default App
