import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { loginUser, registerUser } from '../api/auth-api.js'

function AuthPage({ onAuthed }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  const isRegister = mode === 'register'

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError(null)

    const result = isRegister
      ? await registerUser(email, password, displayName)
      : await loginUser(email, password)

    if (!result.success) {
      setError(result.message)
      return
    }

    await onAuthed()
    navigate('/')
  }

  const toggleMode = () => {
    setError(null)
    setMode(isRegister ? 'login' : 'register')
  }

  return (
    <form onSubmit={handleSubmit}>
      <h1>{isRegister ? 'Create account' : 'Login'}</h1>

      {isRegister && (
        <label>
          Display name
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
          />
        </label>
      )}

      <label>
        Email
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </label>

      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>

      {error && <p role="alert">{error}</p>}

      <button type="submit">{isRegister ? 'Register' : 'Login'}</button>
      <button type="button" onClick={toggleMode}>
        {isRegister ? 'Have an account? Login' : 'New here? Register'}
      </button>
    </form>
  )
}

export default AuthPage
