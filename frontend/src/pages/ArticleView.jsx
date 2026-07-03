import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchArticle } from '../api/articles-api.js'
import { formatCents } from '../format.js'

function ArticleView() {
  const { articleId } = useParams()
  // undefined = loading, null = not found / failed, object = loaded
  const [article, setArticle] = useState()

  useEffect(() => {
    setArticle(undefined)
    fetchArticle(articleId).then(setArticle)
  }, [articleId])

  if (article === undefined) return <p>Loading article...</p>
  if (article === null) return <p>Article not found.</p>

  const canEdit = article.status !== undefined

  return (
    <article>
      <h1>{article.title}</h1>
      <p>
        by {article.author_name} · {formatCents(article.price_cents)}
        {canEdit && ` · ${article.status}`}
        {canEdit && (
          <>
            {' · '}
            <Link to={`/write/${article.id}`}>Edit</Link>
          </>
        )}
      </p>
      <p>{article.summary}</p>

      {article.body ? (
        <div style={{ whiteSpace: 'pre-wrap' }}>{article.body}</div>
      ) : (
        <p>
          <em>Full article available for {formatCents(article.price_cents)}.</em>
        </p>
      )}
    </article>
  )
}

export default ArticleView
