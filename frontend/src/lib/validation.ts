const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export const isEmail = (value: string) => EMAIL.test(value.trim())

export function validateEmail(value: string): string | null {
  if (!value.trim()) return 'Enter your email address.'
  if (!EMAIL.test(value.trim())) return 'Enter a valid email address, like name@company.com.'
  return null
}

export function validatePassword(value: string, forSignup: boolean): string | null {
  if (!value) return 'Enter your password.'
  if (forSignup && value.length < 8) return 'Use at least 8 characters.'
  if (value.length > 200) return 'Use 200 characters or fewer.'
  return null
}

export function validateName(value: string): string | null {
  if (!value.trim()) return 'Enter your name.'
  if (value.trim().length > 120) return 'Use 120 characters or fewer.'
  return null
}

/** Only allow internal redirects after sign in. */
export function safeNext(next: string | null): string {
  if (!next || !next.startsWith('/') || next.startsWith('//')) return '/'
  return next
}
