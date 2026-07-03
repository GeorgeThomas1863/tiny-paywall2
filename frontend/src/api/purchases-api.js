import { sendOperation } from './request.js'

export const purchaseArticle = async (articleId) =>
  sendOperation('/purchases', { method: 'POST', body: { article_id: articleId } }, 'Purchase failed')
