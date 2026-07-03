import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { createArticle, deleteArticle, fetchArticle, updateArticle } from '../api/articles-api.js'

function ArticleEditor() {
  const { articleId } = useParams()
  const navigate = useNavigate()
  const isNew = articleId === undefined

  const [title, setTitle] = useState('')
  const [summary, setSummary] = useState('')
  const [body, setBody] = useState('')
  const [priceCents, setPriceCents] = useState(25)
  const [isPublished, setIsPublished] = useState(false)
  const [error, setError] = useState(null)
  const [loaded, setLoaded] = useState(isNew)

  useEffect(() => {
    if (isNew) return
    fetchArticle(articleId).then((article) => {
      if (article === null || article.body === undefined) {
        setError('Article not found or not yours to edit')
        return
      }
      setTitle(article.title)
      setSummary(article.summary)
      setBody(article.body)
      setPriceCents(article.price_cents)
      setIsPublished(article.status === 'published')
      setLoaded(true)
    })
  }, [articleId, isNew])

  const handleSave = async (event) => {
    event.preventDefault()
    setError(null)

    const fields = {
      title,
      summary,
      body,
      price_cents: Number(priceCents),
      status: isPublished ? 'published' : 'draft',
    }

    const result = isNew
      ? await createArticle({ title, summary, body, price_cents: Number(priceCents) })
      : await updateArticle(articleId, fields)

    if (!result.success) {
      setError(result.message)
      return
    }

    if (isNew && isPublished) {
      await updateArticle(result.id, { status: 'published' })
    }
    navigate('/write')
  }

  const handleDelete = async () => {
    if (!window.confirm('Delete this article? This cannot be undone.')) return

    const result = await deleteArticle(articleId)
    if (!result.success) {
      setError(result.message)
      return
    }
    navigate('/write')
  }

  if (!loaded && !error) return <p>Loading article...</p>
  if (!loaded && error) return <p role="alert">{error}</p>

  return (
    <form onSubmit={handleSave}>
      <h1>{isNew ? 'New article' : 'Edit article'}</h1>

      <label>
        Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </label>

      <label>
        Summary (public teaser)
        <textarea value={summary} onChange={(e) => setSummary(e.target.value)} required />
      </label>

      <label>
        Body (paid content)
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={12} required />
      </label>

      <label>
        Price in cents (1–500)
        <input
          type="number"
          min="1"
          max="500"
          value={priceCents}
          onChange={(e) => setPriceCents(e.target.value)}
          required
        />
      </label>

      <label>
        <input
          type="checkbox"
          checked={isPublished}
          onChange={(e) => setIsPublished(e.target.checked)}
        />
        Published
      </label>

      {error && <p role="alert">{error}</p>}

      <button type="submit">Save</button>
      {!isNew && (
        <button type="button" onClick={handleDelete}>
          Delete
        </button>
      )}
    </form>
  )
}

export default ArticleEditor
