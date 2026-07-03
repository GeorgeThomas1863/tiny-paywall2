import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteArticle, fetchAllArticles, updateArticle } from '../api/articles-api.js'
import { formatCents } from '../format.js'

function AdminPage({ user }) {
  // undefined = loading, null = failed, array = loaded
  const [articles, setArticles] = useState()
  const [error, setError] = useState(null)

  const loadArticles = () => {
    fetchAllArticles().then(setArticles)
  }

  useEffect(() => {
    if (user?.is_admin) loadArticles()
  }, [user])

  if (!user?.is_admin) return <p>Admin only.</p>
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
    <section>
      <h1>Admin — all articles</h1>
      {error && <p role="alert">{error}</p>}

      {articles.length === 0 ? (
        <p>No articles on the platform.</p>
      ) : (
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
                  <button onClick={() => handleToggleStatus(article)}>
                    {article.status === 'published' ? 'Unpublish' : 'Publish'}
                  </button>{' '}
                  <button onClick={() => handleDelete(article)}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

export default AdminPage
