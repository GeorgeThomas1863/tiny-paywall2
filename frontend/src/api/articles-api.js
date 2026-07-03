import { sendRequest, extractErrorMessage } from './request.js'

export const fetchArticles = async () => {
  const { status, data } = await sendRequest('/articles')
  if (status !== 200) return null
  return data
}

export const fetchArticle = async (articleId) => {
  const { status, data } = await sendRequest(`/articles/${articleId}`)
  if (status !== 200) return null
  return data
}

export const fetchMyArticles = async () => {
  const { status, data } = await sendRequest('/articles/mine')
  if (status !== 200) return null
  return data
}

export const fetchAllArticles = async () => {
  const { status, data } = await sendRequest('/articles/all')
  if (status !== 200) return null
  return data
}

export const createArticle = async (fields) => {
  const { status, data } = await sendRequest('/articles', { method: 'POST', body: fields })
  if (status !== 200) {
    return { success: false, message: extractErrorMessage(data, 'Failed to create article') }
  }
  return data
}

export const updateArticle = async (articleId, fields) => {
  const { status, data } = await sendRequest(`/articles/${articleId}`, {
    method: 'PUT',
    body: fields,
  })
  if (status !== 200) {
    return { success: false, message: extractErrorMessage(data, 'Failed to update article') }
  }
  return data
}

export const deleteArticle = async (articleId) => {
  const { status, data } = await sendRequest(`/articles/${articleId}`, { method: 'DELETE' })
  if (status !== 200) {
    return { success: false, message: extractErrorMessage(data, 'Failed to delete article') }
  }
  return data
}
