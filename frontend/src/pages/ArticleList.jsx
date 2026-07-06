import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchArticles } from '../api/articles-api.js'
import { avatarGradient, formatCents, formatDate, formatPoints } from '../format.js'

function ArticleList({ user }) {
  // undefined = loading, null = failed, array = loaded
  const [articles, setArticles] = useState()
  const [view, setView] = useState('new')
  const [query, setQuery] = useState('')

  // owned flags depend on who is logged in — refetch whenever auth changes
  useEffect(() => {
    fetchArticles().then(setArticles)
  }, [user])

  if (articles === undefined) return <p>Loading articles...</p>
  if (articles === null) return <p role="alert">Couldn't load articles. Try refreshing.</p>
  if (articles.length === 0) return <p>No articles published yet.</p>

  // the library view vanishes on logout — fall back to the default view
  const activeView = !user && view === 'library' ? 'new' : view
  const visibleArticles = buildVisibleArticles(articles, activeView, query)

  return (
    <div className="landing">
      <BrowseSidebar user={user} view={activeView} onViewChange={setView} />
      <section className="feed">
        <input
          type="search"
          className="feed-search"
          placeholder="Search articles and authors…"
          aria-label="Search articles"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {visibleArticles.length === 0 ? (
          <p>No articles match — try another view or search.</p>
        ) : (
          visibleArticles.map((article) => (
            <ArticleRow key={article.id} article={article} user={user} />
          ))
        )}
      </section>
      <TopAuthorsPanel articles={articles} />
    </div>
  )
}

//---

function BrowseSidebar({ user, view, onViewChange }) {
  const views = buildBrowseViews(user)

  return (
    <nav className="browse" aria-label="Browse views">
      {views.map((v) => (
        <button
          key={v.id}
          className={view === v.id ? 'browse-link on' : 'browse-link'}
          onClick={() => onViewChange(v.id)}
        >
          <span aria-hidden="true">{v.icon}</span> {v.label}
        </button>
      ))}
    </nav>
  )
}

function ArticleRow({ article, user }) {
  const action = buildArticleAction(article, user)

  return (
    <article className="feed-row">
      <div className="feed-score" title={formatPoints(article.score)}>
        <span className="feed-score-arrow" aria-hidden="true">
          ▲
        </span>
        <span className="feed-score-value">{article.score}</span>
      </div>
      <div className="feed-body">
        <h2>
          <Link to={`/articles/${article.id}`}>{article.title}</Link>
        </h2>
        <p className="feed-summary">{article.summary}</p>
        <p className="feed-meta">
          by <b>{article.author_name}</b> · {formatDate(article.created_at)}
          {!action.showsPrice && <> · {formatCents(article.price_cents)}</>}
        </p>
      </div>
      <Link to={action.to} className={action.accent ? 'feed-action accent' : 'feed-action'}>
        {action.label}
      </Link>
    </article>
  )
}

function TopAuthorsPanel({ articles }) {
  const topAuthors = buildTopAuthors(articles)
  if (topAuthors.length === 0) return null

  return (
    <aside className="rail">
      <div className="panel">
        <h3>
          <span aria-hidden="true">🏆</span> Top authors
        </h3>
        {topAuthors.map((author) => (
          <p key={author.name} className="rail-author">
            <span className="avatar" style={avatarGradient(author.name)} aria-hidden="true" />
            {author.name}
            <span className="rail-points">{formatPoints(author.points)}</span>
          </p>
        ))}
      </div>
    </aside>
  )
}

//--- pure builders ---

const buildBrowseViews = (user) => {
  const views = [
    { id: 'new', icon: '✨', label: 'Newest' },
    { id: 'top', icon: '🔥', label: 'Top rated' },
    { id: 'cheap', icon: '🪙', label: 'Under 25¢' },
  ]
  if (user) views.push({ id: 'library', icon: '📚', label: 'My library' })
  return views
}

const buildVisibleArticles = (articles, view, query) => {
  const needle = query.trim().toLowerCase()
  const matched = []

  for (const article of articles) {
    if (needle && !matchesQuery(article, needle)) continue
    if (view === 'cheap' && article.price_cents >= 25) continue
    if (view === 'library' && !article.purchased) continue
    matched.push(article)
  }

  if (view === 'top') matched.sort((a, b) => b.score - a.score)
  return matched
}

const matchesQuery = (article, needle) =>
  article.title.toLowerCase().includes(needle) ||
  article.summary.toLowerCase().includes(needle) ||
  article.author_name.toLowerCase().includes(needle)

const buildArticleAction = (article, user) => {
  if (user && article.author_name === user.display_name) {
    return { to: `/articles/${article.id}`, label: 'Yours', accent: false, showsPrice: false }
  }
  if (article.owned) {
    return { to: `/articles/${article.id}`, label: 'Read', accent: false, showsPrice: false }
  }
  if (user) {
    return {
      to: `/articles/${article.id}`,
      label: `Unlock ${formatCents(article.price_cents)}`,
      accent: true,
      showsPrice: true,
    }
  }
  return { to: '/login', label: 'Login to buy', accent: true, showsPrice: false }
}

const buildTopAuthors = (articles) => {
  const totals = {}
  for (const article of articles) {
    totals[article.author_name] = (totals[article.author_name] || 0) + article.score
  }

  const authors = []
  for (const name of Object.keys(totals)) {
    authors.push({ name, points: totals[name] })
  }

  authors.sort((a, b) => b.points - a.points)
  return authors.slice(0, 5)
}

export default ArticleList
