import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchWalletHistory, startTopup } from '../api/wallet-api.js'
import { formatCents } from '../format.js'

// Mirrored in backend/routes/wallet.py TOPUP_AMOUNTS_CENTS — keep in sync.
const TOPUP_OPTIONS_CENTS = [500, 1000, 2000]
const CONFIRM_POLL_MS = 2000
const CONFIRM_MAX_ATTEMPTS = 10

function AccountPage({ user, onUserChange }) {
  // undefined = loading, null = failed, array = loaded
  const [history, setHistory] = useState()
  const [error, setError] = useState(null)
  const confirmState = useTopupConfirmation(onUserChange, setHistory)

  useEffect(() => {
    fetchWalletHistory().then(setHistory)
  }, [])

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

      <ConfirmationNotice confirmState={confirmState} />

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
      <HistoryTable history={history} />
    </section>
  )
}

// Watches for the ?topup=success&session_id=... return from Stripe Checkout and
// polls the ledger until that exact top-up lands (the webhook may lag the redirect).
function useTopupConfirmation(onUserChange, onHistoryLoaded) {
  const [searchParams, setSearchParams] = useSearchParams()
  const [confirmState, setConfirmState] = useState(null) // null | waiting | confirmed | timeout

  useEffect(() => {
    if (searchParams.get('topup') !== 'success') return
    const sessionId = searchParams.get('session_id')
    if (!sessionId) return

    setConfirmState('waiting')
    let attempts = 0
    let timer = null

    const finish = (state) => {
      clearInterval(timer)
      setConfirmState(state)
      setSearchParams({}, { replace: true })
    }

    const checkForTopup = async () => {
      attempts += 1
      const entries = await fetchWalletHistory()
      const landed = entries?.some((entry) => entry.stripe_session_id === sessionId)

      if (landed) {
        onHistoryLoaded(entries)
        await onUserChange()
        finish('confirmed')
        return
      }
      if (attempts >= CONFIRM_MAX_ATTEMPTS) finish('timeout')
    }

    timer = setInterval(checkForTopup, CONFIRM_POLL_MS)
    return () => clearInterval(timer)
  }, [searchParams])

  return confirmState
}

//---

function ConfirmationNotice({ confirmState }) {
  if (confirmState === 'waiting') return <p>Confirming your payment…</p>
  if (confirmState === 'confirmed') return <p>Payment received — balance updated.</p>
  if (confirmState === 'timeout') {
    return <p role="alert">Payment is still processing — refresh in a moment.</p>
  }
  return null
}

function HistoryTable({ history }) {
  if (history === undefined) return <p>Loading history…</p>
  if (history === null) return <p role="alert">Couldn't load history. Try refreshing.</p>
  if (history.length === 0) return <p>No transactions yet.</p>

  return (
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
  )
}

export default AccountPage
