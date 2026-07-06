import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchArticle } from '../api/articles-api.js'
import { purchaseArticle } from '../api/purchases-api.js'
import { voteArticle } from '../api/votes-api.js'
import { avatarGradient, formatCents, formatDate, formatPoints } from '../format.js'

function ArticleView({ user, onUserChange }) {
  const { articleId } = useParams()
  // undefined = loading, null = not found / failed, object = loaded
  const [article, setArticle] = useState()
  const [error, setError] = useState(null)
  const [unlocking, setUnlocking] = useState(false)

  useEffect(() => {
    setArticle(undefined)
    setError(null)
    fetchArticle(articleId).then(setArticle)
  }, [articleId])

  const handleUnlock = async () => {
    setError(null)
    setUnlocking(true)
    const result = await purchaseArticle(articleId)
    setUnlocking(false)

    if (!result.success) {
      setError(result.message)
      return
    }

    const [fresh] = await Promise.all([fetchArticle(articleId), onUserChange()])
    if (fresh === null) {
      setError('Purchase complete — refresh the page to read your article.')
      return
    }
    setArticle(fresh)
  }

  if (article === undefined) return <p>Loading article...</p>
  if (article === null) return <p>Article not found.</p>

  return (
    <article className="article-card">
      <ArticleHead article={article} onVoted={setArticle} />
      <h1>{article.title}</h1>
      <p className="lede">{article.summary}</p>

      {article.body ? (
        <div className="article-body">{article.body}</div>
      ) : (
        <UnlockPrompt
          article={article}
          user={user}
          unlocking={unlocking}
          error={error}
          onUnlock={handleUnlock}
        />
      )}
    </article>
  )
}

//---

function ArticleHead({ article, onVoted }) {
  const canEdit = article.status !== undefined

  return (
    <header className="article-head">
      <span
        className="avatar"
        style={avatarGradient(article.author_name)}
        aria-hidden="true"
      />
      <span className="article-byline">
        by <b>{article.author_name}</b> · {formatDate(article.created_at)} ·{' '}
        {formatCents(article.price_cents)}
        {canEdit && (
          <>
            {' '}
            <span className="status-chip">{article.status}</span>{' '}
            <Link to={`/write/${article.id}`}>Edit</Link>
          </>
        )}
      </span>
      {article.my_vote !== null ? (
        <VoteControls article={article} onVoted={onVoted} />
      ) : (
        <span className="vote-pill" title={formatPoints(article.score)}>
          <span aria-hidden="true">▲</span> {article.score}
        </span>
      )}
    </header>
  )
}

function VoteControls({ article, onVoted }) {
  const [voting, setVoting] = useState(false)
  const [error, setError] = useState(null)

  const handleVote = async (arrowValue) => {
    const value = article.my_vote === arrowValue ? 0 : arrowValue
    setError(null)
    setVoting(true)
    const result = await voteArticle(article.id, value)
    setVoting(false)

    if (!result.success) {
      setError(result.message)
      return
    }
    onVoted({ ...article, score: result.score, my_vote: result.my_vote })
  }

  return (
    <span className="vote-pill">
      <button
        aria-label="Upvote"
        aria-pressed={article.my_vote === 1}
        disabled={voting}
        onClick={() => handleVote(1)}
      >
        ▲
      </button>
      {article.score}
      <button
        aria-label="Downvote"
        aria-pressed={article.my_vote === -1}
        disabled={voting}
        onClick={() => handleVote(-1)}
      >
        ▼
      </button>
      {error && <span role="alert">{error}</span>}
    </span>
  )
}

function UnlockPrompt({ article, user, unlocking, error, onUnlock }) {
  if (!user) {
    return (
      <div className="unlock-gate">
        <p>
          <Link to="/login">Log in</Link> to unlock this article for{' '}
          {formatCents(article.price_cents)}.
        </p>
      </div>
    )
  }

  const canAfford = user.wallet_cents >= article.price_cents

  return (
    <div className="unlock-gate">
      <p className="unlock-note">
        You've reached the end of the free preview.
      </p>
      <button className="unlock-btn" onClick={onUnlock} disabled={unlocking || !canAfford}>
        {unlocking ? 'Unlocking…' : `Unlock for ${formatCents(article.price_cents)}`}
      </button>
      {!canAfford && (
        <p>
          Balance {formatCents(user.wallet_cents)} — price{' '}
          {formatCents(article.price_cents)}. <Link to="/account">Add funds</Link>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  )
}

export default ArticleView
