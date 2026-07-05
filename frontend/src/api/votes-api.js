import { sendOperation } from './request.js'

export const voteArticle = async (articleId, value) =>
  sendOperation(`/articles/${articleId}/vote`, { method: 'PUT', body: { value } }, 'Vote failed')
