import { useState, useEffect } from 'react'
import { fetchHelloMessage } from './api/hello-api.js'

function App() {
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchHelloMessage()
      .then(setMessage)
      .catch((err) => setError(err.message))
  }, [])

  if (error) return <p>Error: {error}</p>
  if (!message) return <p>Loading...</p>
  return <h1>{message}</h1>
}

export default App
