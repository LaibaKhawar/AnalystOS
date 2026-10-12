import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { setUnauthorizedHandler, tokenStore } from '@/api/client'
import { authApi } from '@/api/endpoints'
import type { LoginInput, RegisterInput, TokenResponse, User } from '@/api/types'
import { qk } from '@/hooks/queries/keys'
import { AuthContext } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const [token, setToken] = useState<string | null>(() => tokenStore.get())

  const me = useQuery({
    queryKey: qk.me,
    queryFn: authApi.me,
    enabled: Boolean(token),
    retry: false,
    staleTime: 300_000,
  })

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null)
      client.clear()
      const here = window.location.pathname
      if (!['/login', '/register', '/welcome'].includes(here)) {
        navigate(`/login?next=${encodeURIComponent(here + window.location.search)}`, { replace: true })
      }
    })
    return () => setUnauthorizedHandler(null)
  }, [client, navigate])

  const accept = useCallback(
    (response: TokenResponse): User => {
      tokenStore.set(response.access_token)
      client.clear()
      client.setQueryData(qk.me, response.user)
      setToken(response.access_token)
      return response.user
    },
    [client],
  )

  const login = useCallback(async (input: LoginInput) => accept(await authApi.login(input)), [accept])
  const register = useCallback(async (input: RegisterInput) => accept(await authApi.register(input)), [accept])
  const logout = useCallback(() => {
    tokenStore.clear()
    setToken(null)
    client.clear()
    navigate('/welcome', { replace: true })
  }, [client, navigate])

  const value = useMemo(
    () => ({
      user: token ? (me.data ?? null) : null,
      isAuthenticated: Boolean(token),
      isLoading: Boolean(token) && me.isPending,
      login,
      register,
      logout,
    }),
    [token, me.data, me.isPending, login, register, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
