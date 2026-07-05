export const formatCents = (cents) => {
  if (cents < 100) return `${cents}¢`
  return `$${(cents / 100).toFixed(2)}`
}

export const formatPoints = (score) => {
  if (score === 1 || score === -1) return `${score} point`
  return `${score} points`
}
