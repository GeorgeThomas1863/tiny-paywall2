export const formatCents = (cents) => {
  if (cents < 100) return `${cents}¢`
  return `$${(cents / 100).toFixed(2)}`
}
