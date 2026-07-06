export const formatCents = (cents) => {
  if (cents < 100) return `${cents}¢`
  return `$${(cents / 100).toFixed(2)}`
}

export const formatPoints = (score) => {
  if (score === 1 || score === -1) return `${score} point`
  return `${score} points`
}

export const formatDate = (isoString) => {
  const date = new Date(isoString)
  if (Number.isNaN(date.getTime())) return ''
  const sameYear = date.getFullYear() === new Date().getFullYear()
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: sameYear ? undefined : 'numeric',
  })
}

export const avatarGradient = (name) => {
  let hue = 0
  for (let i = 0; i < name.length; i++) {
    hue = (hue * 31 + name.charCodeAt(i)) % 360
  }
  return {
    background: `linear-gradient(135deg, hsl(${hue} 65% 58%), hsl(${(hue + 70) % 360} 65% 48%))`,
  }
}
