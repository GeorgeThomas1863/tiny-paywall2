import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchArticle } from '../api/articles-api.js'
import { formatCents } from '../format.js'

function ArticleView() {
  const { articleId } = useParams()
  const [article, setArticle] = useState(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    fetchArticle(articleId).then((data) => {
      if (data === null) setNotFound(true)
      setArticle(data)
    })
  }, [articleId])

  if (notFound) return <p>Article not found.</p>
  if (article === null) return <p>Loading article...</p>

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
