import { fetchData, sendOperation } from './request.js'

export const fetchArticles = async () => fetchData('/articles')

export const fetchArticle = async (articleId) => fetchData(`/articles/${articleId}`)

export const fetchMyArticles = async () => fetchData('/articles/mine')

export const fetchAllArticles = async () => fetchData('/articles/all')

export const createArticle = async (fields) =>
  sendOperation('/articles', { method: 'POST', body: fields }, 'Failed to create article')

export const updateArticle = async (articleId, fields) =>
  sendOperation(`/articles/${articleId}`, { method: 'PUT', body: fields }, 'Failed to update article')

export const deleteArticle = async (articleId) =>
  sendOperation(`/articles/${articleId}`, { method: 'DELETE' }, 'Failed to delete article')
