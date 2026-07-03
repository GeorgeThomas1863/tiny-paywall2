import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchMyArticles } from '../api/articles-api.js'
import { formatCents } from '../format.js'

function MyArticles() {
  const [articles, setArticles] = useState(null)

  useEffect(() => {
    fetchMyArticles().then(setArticles)
  }, [])

  if (articles === null) return <p>Loading your articles...</p>

  return (
    <section>
      <h1>My articles</h1>
      <p>
        <Link to="/write/new">New article</Link>
      </p>

      {articles.length === 0 ? (
        <p>You haven't written anything yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Status</th>
              <th>Price</th>
              <th>Sales</th>
              <th>Earned</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {articles.map((article) => (
              <tr key={article.id}>
                <td>
                  <Link to={`/articles/${article.id}`}>{article.title}</Link>
                </td>
                <td>{article.status}</td>
                <td>{formatCents(article.price_cents)}</td>
                <td>{article.sales_count}</td>
                <td>{formatCents(article.earned_cents)}</td>
                <td>
                  <Link to={`/write/${article.id}`}>Edit</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export default MyArticles
