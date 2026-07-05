import { fetchData, sendOperation } from './request.js'

export const requestPayout = async (destination) =>
  sendOperation(
    '/payouts/request',
    { method: 'POST', body: { destination } },
    'Failed to request payout'
  )

export const fetchMyPayouts = async () => fetchData('/payouts/mine')

export const fetchAllPayouts = async (status) =>
  fetchData(status ? `/payouts?status=${status}` : '/payouts')

export const resolvePayout = async (payoutId, status) =>
  sendOperation(
    `/payouts/${payoutId}`,
    { method: 'PUT', body: { status } },
    'Failed to resolve payout'
  )
