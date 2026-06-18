const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const fetchHelloMessage = async () => {
  const response = await fetch(`${API_URL}/hello`)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const data = await response.json()
  return data.message
}
