import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '@/api/client'
import { Field } from '@/components/forms/Field'
import { FormError } from '@/components/forms/FormError'
import { AuthLayout } from '@/components/layout/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { validateEmail, validatePassword } from '@/lib/validation'
import { useAuth } from '@/providers/auth-context'

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null }>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const next = { email: validateEmail(email), password: validatePassword(password, false) }
    setErrors(next)
    if (next.email || next.password) return
    setPending(true)
    setFormError(null)
    try {
      await login({ email: email.trim(), password })
      // PublicOnly redirects once the session is set
    } catch (error) {
      setFormError(errorMessage(error))
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout
      title="Sign in to AnalystOS"
      subtitle="Pick up where your last analysis left off."
      footer={
        <>
          New here?{' '}
          <Link to="/register" className="text-brand-text font-medium underline-offset-4 hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <Field label="Email" error={errors.email}>
          {(p) => (
            <Input {...p} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          )}
        </Field>
        <Field label="Password" error={errors.password}>
          {(p) => (
            <Input
              {...p}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" size="lg" disabled={pending} className="mt-2 w-full">
          {pending ? 'Signing in' : 'Sign in'}
        </Button>
      </form>
    </AuthLayout>
  )
}
