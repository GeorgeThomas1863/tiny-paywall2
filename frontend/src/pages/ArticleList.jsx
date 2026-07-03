import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchArticles } from '../api/articles-api.js'
import { formatCents } from '../format.js'

function ArticleList() {
  // undefined = loading, null = failed, array = loaded
  const [articles, setArticles] = useState()

  useEffect(() => {
    fetchArticles().then(setArticles)
  }, [])

  if (articles === undefined) return <p>Loading articles...</p>
  if (articles === null) return <p role="alert">Couldn't load articles. Try refreshing.</p>
  if (articles.length === 0) return <p>No articles published yet.</p>

  return (
    <section>
      {articles.map((article) => (
        <article key={article.id}>
          <h2>
            <Link to={`/articles/${article.id}`}>{article.title}</Link>
          </h2>
          <p>
            by {article.author_name} · {formatCents(article.price_cents)}
            {article.owned && ' · owned'}
          </p>
          <p>{article.summary}</p>
        </article>
      ))}
    </section>
  )
}

export default ArticleList
