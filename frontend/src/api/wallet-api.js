import { fetchData, sendOperation } from './request.js'

export const startTopup = async (amountCents) =>
  sendOperation(
    '/wallet/topup',
    { method: 'POST', body: { amount_cents: amountCents } },
    'Failed to start top-up'
  )

export const fetchWalletHistory = async () => fetchData('/wallet/history')
