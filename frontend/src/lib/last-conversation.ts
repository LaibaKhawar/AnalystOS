const KEY = 'analystos.lastConversation'

export function rememberConversation(id: string): void {
  try {
    localStorage.setItem(KEY, id)
  } catch {
    /* ignore */
  }
}

export function lastConversation(): string | null {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function forgetConversation(id?: string): void {
  try {
    if (!id || localStorage.getItem(KEY) === id) localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}
