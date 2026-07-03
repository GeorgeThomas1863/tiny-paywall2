import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { fetchMe, logoutUser } from './api/auth-api.js'
import NavBar from './components/NavBar.jsx'
import AdminPage from './pages/AdminPage.jsx'
import ArticleEditor from './pages/ArticleEditor.jsx'
import ArticleList from './pages/ArticleList.jsx'
import ArticleView from './pages/ArticleView.jsx'
import AuthPage from './pages/AuthPage.jsx'
import MyArticles from './pages/MyArticles.jsx'

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
          <Route path="/" element={<ArticleList />} />
          <Route path="/articles/:articleId" element={<ArticleView />} />
          <Route path="/login" element={<AuthPage onAuthed={refreshUser} />} />
          <Route path="/write" element={<RequireUser user={user}><MyArticles /></RequireUser>} />
          <Route path="/write/new" element={<RequireUser user={user}><ArticleEditor /></RequireUser>} />
          <Route path="/write/:articleId" element={<RequireUser user={user}><ArticleEditor /></RequireUser>} />
          <Route path="/admin" element={<RequireUser user={user}><AdminPage user={user} /></RequireUser>} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </>
  )
}

function RequireUser({ user, children }) {
  if (!user) return <Navigate to="/login" replace />
  return children
}

export default App
