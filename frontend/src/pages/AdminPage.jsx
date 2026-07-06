import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteArticle, fetchAllArticles, updateArticle } from '../api/articles-api.js'
import { fetchAllPayouts, resolvePayout } from '../api/payouts-api.js'
import { formatCents } from '../format.js'

const PAYOUT_FILTERS = ['requested', 'paid', 'rejected', 'all']

function AdminPage({ user }) {
  const [tab, setTab] = useState('articles')

  if (!user?.is_admin) return <p>Admin only.</p>

  return (
    <section>
      <h1>Admin</h1>
      <p>
        <button onClick={() => setTab('articles')} disabled={tab === 'articles'}>
          Articles
        </button>{' '}
        <button onClick={() => setTab('payouts')} disabled={tab === 'payouts'}>
          Payouts
        </button>
      </p>

      {tab === 'articles' ? <ArticlesTab /> : <PayoutsTab />}
    </section>
  )
}

//--- articles tab ---

function ArticlesTab() {
  // undefined = loading, null = failed, array = loaded
  const [articles, setArticles] = useState()
  const [error, setError] = useState(null)

  const loadArticles = () => {
    fetchAllArticles().then(setArticles)
  }

  useEffect(loadArticles, [])

  if (articles === undefined) return <p>Loading all articles...</p>
  if (articles === null) return <p role="alert">Couldn't load articles. Try refreshing.</p>

  const handleToggleStatus = async (article) => {
    const nextStatus = article.status === 'published' ? 'draft' : 'published'
    const result = await updateArticle(article.id, { status: nextStatus })
    if (!result.success) {
      setError(result.message)
      return
    }
    loadArticles()
  }

  const handleDelete = async (article) => {
    if (!window.confirm(`Delete "${article.title}" by ${article.author_name}?`)) return
    const result = await deleteArticle(article.id)
    if (!result.success) {
      setError(result.message)
      return
    }
    loadArticles()
  }

  return (
    <div>
      <h2>All articles</h2>
      {error && <p role="alert">{error}</p>}

      {articles.length === 0 ? (
        <p>No articles on the platform.</p>
      ) : (
        <ArticlesTable
          articles={articles}
          onToggleStatus={handleToggleStatus}
          onDelete={handleDelete}
        />
      )}
    </div>
  )
}

function ArticlesTable({ articles, onToggleStatus, onDelete }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Title</th>
          <th>Author</th>
          <th>Status</th>
          <th>Price</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {articles.map((article) => (
          <tr key={article.id}>
            <td>
              <Link to={`/articles/${article.id}`}>{article.title}</Link>
            </td>
            <td>{article.author_name}</td>
            <td>{article.status}</td>
            <td>{formatCents(article.price_cents)}</td>
            <td>
              <Link to={`/write/${article.id}`}>Edit</Link>{' '}
              <button onClick={() => onToggleStatus(article)}>
                {article.status === 'published' ? 'Unpublish' : 'Publish'}
              </button>{' '}
              <button onClick={() => onDelete(article)}>Delete</button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

//--- payouts tab ---

function PayoutsTab() {
  const [statusFilter, setStatusFilter] = useState('requested')
  // undefined = loading, null = failed, array = loaded
  const [payouts, setPayouts] = useState()
  const [error, setError] = useState(null)

  const loadPayouts = () => {
    fetchAllPayouts(statusFilter === 'all' ? null : statusFilter).then(setPayouts)
  }

  useEffect(loadPayouts, [statusFilter])

  const handleResolve = async (payout, status) => {
    const action = status === 'paid' ? 'Mark paid' : 'Reject and return funds'
    const summary = `${formatCents(payout.amount_cents)} to ${payout.display_name} (${payout.destination})`
    if (!window.confirm(`${action}: ${summary}?`)) return

    setError(null)
    const result = await resolvePayout(payout.id, status)
    if (!result.success) {
      setError(result.message)
      return
    }
    loadPayouts()
  }

  return (
    <div>
      <h2>Payout requests</h2>
      <p>
        Show:{' '}
        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
          {PAYOUT_FILTERS.map((filter) => (
            <option key={filter} value={filter}>
              {filter}
            </option>
          ))}
        </select>
      </p>
      {error && <p role="alert">{error}</p>}

      <PayoutQueue payouts={payouts} onResolve={handleResolve} />
    </div>
  )
}

function PayoutQueue({ payouts, onResolve }) {
  if (payouts === undefined) return <p>Loading payout requests...</p>
  if (payouts === null) return <p role="alert">Couldn't load payout requests. Try refreshing.</p>
  if (payouts.length === 0) return <p>No payout requests here.</p>

  return (
    <table>
      <thead>
        <tr>
          <th>When</th>
          <th>Requester</th>
          <th>Amount</th>
          <th>Destination</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {payouts.map((payout) => (
          <tr key={payout.id}>
            <td>{new Date(payout.created_at).toLocaleString()}</td>
            <td>
              {payout.display_name} ({payout.email})
            </td>
            <td>{formatCents(payout.amount_cents)}</td>
            <td>{payout.destination}</td>
            <td>
              <span className={`status-chip status-${payout.status}`}>{payout.status}</span>
            </td>
            <td>
              {payout.status === 'requested' && (
                <>
                  <button onClick={() => onResolve(payout, 'paid')}>Mark paid</button>{' '}
                  <button onClick={() => onResolve(payout, 'rejected')}>Reject</button>
                </>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default AdminPage
