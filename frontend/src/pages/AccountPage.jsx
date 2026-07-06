import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchMyPayouts, requestPayout } from '../api/payouts-api.js'
import { fetchWalletHistory, startTopup } from '../api/wallet-api.js'
import { avatarGradient, formatCents } from '../format.js'

// Mirrored in backend/routes/wallet.py TOPUP_AMOUNTS_CENTS — keep in sync.
const TOPUP_OPTIONS_CENTS = [500, 1000, 2000]
// Mirrored in backend/money/operations.py PAYOUT_MINIMUM_CENTS — keep in sync.
const PAYOUT_MINIMUM_CENTS = 1000
const CONFIRM_POLL_MS = 2000
const CONFIRM_MAX_ATTEMPTS = 10

function AccountPage({ user, onUserChange }) {
  // undefined = loading, null = failed, array = loaded (both)
  const [history, setHistory] = useState()
  const [payouts, setPayouts] = useState()
  const [error, setError] = useState(null)
  const confirmState = useTopupConfirmation(onUserChange, setHistory)

  const loadHistory = () => {
    fetchWalletHistory().then(setHistory)
  }

  const loadPayouts = () => {
    fetchMyPayouts().then(setPayouts)
  }

  useEffect(() => {
    loadHistory()
    loadPayouts()
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

  // A payout reserve moves earnings into a request — the requests list, the
  // ledger, and the balance chip all change, so refresh all three.
  const handlePayoutRequested = async () => {
    loadPayouts()
    loadHistory()
    await onUserChange()
  }

  return (
    <section>
      <ProfileHead user={user} />

      <ConfirmationNotice confirmState={confirmState} />

      <div className="stat-grid">
        <WalletCard user={user} onTopup={handleTopup} />
        <EarningsCard user={user} payouts={payouts} onRequested={handlePayoutRequested} />
      </div>
      {error && <p role="alert">{error}</p>}

      <div className="panel">
        <h3>Payout requests</h3>
        <PayoutTable payouts={payouts} />
      </div>

      <div className="panel">
        <h3>History</h3>
        <HistoryTable history={history} />
      </div>
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

function ProfileHead({ user }) {
  return (
    <header className="profile-head">
      <span
        className="avatar avatar-lg"
        style={avatarGradient(user.display_name)}
        aria-hidden="true"
      />
      <div>
        <h1>{user.display_name}</h1>
        <p className="profile-sub">
          {user.email}
          {user.is_admin && (
            <>
              {' '}
              <span className="status-chip">admin</span>
            </>
          )}
        </p>
      </div>
    </header>
  )
}

function WalletCard({ user, onTopup }) {
  return (
    <div className="panel stat-card">
      <h2>Wallet</h2>
      <p className="stat-value">{formatCents(user.wallet_cents)}</p>
      <p className="stat-actions">
        Add funds:{' '}
        {TOPUP_OPTIONS_CENTS.map((amount) => (
          <button key={amount} onClick={() => onTopup(amount)}>
            {formatCents(amount)}
          </button>
        ))}
      </p>
    </div>
  )
}

function EarningsCard({ user, payouts, onRequested }) {
  const belowMinimum = user.earnings_cents < PAYOUT_MINIMUM_CENTS
  const hasPending = Array.isArray(payouts) && payouts.some((p) => p.status === 'requested')

  return (
    <div className="panel stat-card">
      <h2>Earnings</h2>
      <p className="stat-value">{formatCents(user.earnings_cents)}</p>
      <PayoutRequestForm
        belowMinimum={belowMinimum}
        hasPending={hasPending}
        onRequested={onRequested}
      />
    </div>
  )
}

function PayoutRequestForm({ belowMinimum, hasPending, onRequested }) {
  const [destination, setDestination] = useState('')
  const [requesting, setRequesting] = useState(false)
  const [error, setError] = useState(null)

  const handleRequest = async (event) => {
    event.preventDefault()
    setError(null)
    setRequesting(true)
    const result = await requestPayout(destination)
    setRequesting(false)
    if (!result.success) {
      setError(result.message)
      return
    }
    setDestination('')
    await onRequested()
  }

  if (belowMinimum && !hasPending) {
    return (
      <p className="stat-note">
        Payouts unlock at {formatCents(PAYOUT_MINIMUM_CENTS)} of earnings.
      </p>
    )
  }
  if (hasPending) {
    return <p className="stat-note">A payout request is pending — we'll pay it out shortly.</p>
  }

  return (
    <form onSubmit={handleRequest}>
      <label>
        Where should we send the money?{' '}
        <input
          value={destination}
          onChange={(event) => setDestination(event.target.value)}
          placeholder="PayPal: you@example.com"
          maxLength={200}
          required
        />
      </label>{' '}
      <button type="submit" disabled={requesting || !destination.trim()}>
        {requesting ? 'Requesting…' : 'Request payout'}
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
  )
}

function ConfirmationNotice({ confirmState }) {
  if (confirmState === 'waiting') return <p>Confirming your payment…</p>
  if (confirmState === 'confirmed') return <p>Payment received — balance updated.</p>
  if (confirmState === 'timeout') {
    return <p role="alert">Payment is still processing — refresh in a moment.</p>
  }
  return null
}

function PayoutTable({ payouts }) {
  if (payouts === undefined) return <p>Loading payout requests…</p>
  if (payouts === null) return <p role="alert">Couldn't load payout requests. Try refreshing.</p>
  if (payouts.length === 0) return <p>No payout requests yet.</p>

  return (
    <table>
      <thead>
        <tr>
          <th>When</th>
          <th>Amount</th>
          <th>Destination</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        {payouts.map((payout) => (
          <tr key={payout.id}>
            <td>{new Date(payout.created_at).toLocaleString()}</td>
            <td>{formatCents(payout.amount_cents)}</td>
            <td>{payout.destination}</td>
            <td>
              <span className={`status-chip status-${payout.status}`}>{payout.status}</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
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
            <td className={entry.amount_cents > 0 ? 'amount-in' : 'amount-out'}>
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
