import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchWalletHistory, startTopup } from '../api/wallet-api.js'
import { formatCents } from '../format.js'

const TOPUP_OPTIONS_CENTS = [500, 1000, 2000]
const CONFIRM_POLL_MS = 2000
const CONFIRM_MAX_ATTEMPTS = 10

function AccountPage({ user, onUserChange }) {
  // undefined = loading, null = failed, array = loaded
  const [history, setHistory] = useState()
  const [error, setError] = useState(null)
  const [confirmState, setConfirmState] = useState(null) // null | 'waiting' | 'confirmed' | 'timeout'
  const [searchParams, setSearchParams] = useSearchParams()
  const pollAttempts = useRef(0)

  const loadHistory = async () => {
    setHistory(await fetchWalletHistory())
  }

  useEffect(() => {
    loadHistory()
  }, [])

  useEffect(() => {
    if (searchParams.get('topup') !== 'success') return
    const sessionId = searchParams.get('session_id')
    if (!sessionId) return

    setConfirmState('waiting')
    pollAttempts.current = 0

    const timer = setInterval(async () => {
      pollAttempts.current += 1
      const entries = await fetchWalletHistory()
      const found = entries?.some((entry) => entry.stripe_session_id === sessionId)

      if (found) {
        clearInterval(timer)
        setConfirmState('confirmed')
        setHistory(entries)
        await onUserChange()
        setSearchParams({}, { replace: true })
        return
      }
      if (pollAttempts.current >= CONFIRM_MAX_ATTEMPTS) {
        clearInterval(timer)
        setConfirmState('timeout')
        setSearchParams({}, { replace: true })
      }
    }, CONFIRM_POLL_MS)

    return () => clearInterval(timer)
  }, [searchParams])

  const handleTopup = async (amountCents) => {
    setError(null)
    const result = await startTopup(amountCents)
    if (!result.success) {
      setError(result.message)
      return
    }
    window.location.assign(result.url)
  }

  return (
    <section>
      <h1>Account</h1>

      {confirmState === 'waiting' && <p>Confirming your payment…</p>}
      {confirmState === 'confirmed' && <p>Payment received — balance updated.</p>}
      {confirmState === 'timeout' && (
        <p role="alert">Payment is still processing — refresh in a moment.</p>
      )}

      <h2>Wallet: {formatCents(user.wallet_cents)}</h2>
      <p>
        Add funds:{' '}
        {TOPUP_OPTIONS_CENTS.map((amount) => (
          <button key={amount} onClick={() => handleTopup(amount)}>
            {formatCents(amount)}
          </button>
        ))}
      </p>

      <h2>Earnings: {formatCents(user.earnings_cents)}</h2>

      {error && <p role="alert">{error}</p>}

      <h2>History</h2>
      {history === undefined && <p>Loading history…</p>}
      {history === null && <p role="alert">Couldn't load history. Try refreshing.</p>}
      {history && history.length === 0 && <p>No transactions yet.</p>}
      {history && history.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>When</th>
              <th>Type</th>
              <th>Balance</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody>
            {history.map((entry) => (
              <tr key={entry.id}>
                <td>{new Date(entry.created_at).toLocaleString()}</td>
                <td>{entry.type}</td>
                <td>{entry.balance}</td>
                <td>
                  {entry.amount_cents > 0 ? '+' : '−'}
                  {formatCents(Math.abs(entry.amount_cents))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export default AccountPage
