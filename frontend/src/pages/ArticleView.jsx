import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchArticle } from '../api/articles-api.js'
import { purchaseArticle } from '../api/purchases-api.js'
import { voteArticle } from '../api/votes-api.js'
import { formatCents, formatPoints } from '../format.js'

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

  const canEdit = article.status !== undefined

  return (
    <article>
      <h1>{article.title}</h1>
      <p>
        by {article.author_name} · {formatCents(article.price_cents)}
        {article.my_vote === null && ` · ${formatPoints(article.score)}`}
        {canEdit && ` · ${article.status}`}
        {canEdit && (
          <>
            {' · '}
            <Link to={`/write/${article.id}`}>Edit</Link>
          </>
        )}
      </p>
      {article.my_vote !== null && (
        <VoteControls article={article} onVoted={setArticle} />
      )}
      <p>{article.summary}</p>

      {article.body ? (
        <div style={{ whiteSpace: 'pre-wrap' }}>{article.body}</div>
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
    <p>
      <button
        aria-label="Upvote"
        aria-pressed={article.my_vote === 1}
        disabled={voting}
        onClick={() => handleVote(1)}
      >
        ▲
      </button>{' '}
      {article.score}{' '}
      <button
        aria-label="Downvote"
        aria-pressed={article.my_vote === -1}
        disabled={voting}
        onClick={() => handleVote(-1)}
      >
        ▼
      </button>
      {error && <span role="alert"> {error}</span>}
    </p>
  )
}

function UnlockPrompt({ article, user, unlocking, error, onUnlock }) {
  if (!user) {
    return (
      <p>
        <Link to="/login">Log in</Link> to unlock this article for{' '}
        {formatCents(article.price_cents)}.
      </p>
    )
  }

  const canAfford = user.wallet_cents >= article.price_cents

  return (
    <div>
      <button onClick={onUnlock} disabled={unlocking || !canAfford}>
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
