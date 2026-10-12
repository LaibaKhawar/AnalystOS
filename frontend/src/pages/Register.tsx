import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '@/api/client'
import { Field } from '@/components/forms/Field'
import { FormError } from '@/components/forms/FormError'
import { AuthLayout } from '@/components/layout/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { validateEmail, validateName, validatePassword } from '@/lib/validation'
import { useAuth } from '@/providers/auth-context'

type Errors = { name?: string | null; email?: string | null; password?: string | null }

export default function Register() {
  const { register } = useAuth()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState<Errors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const next: Errors = {
      name: validateName(name),
      email: validateEmail(email),
      password: validatePassword(password, true),
    }
    setErrors(next)
    if (next.name || next.email || next.password) return
    setPending(true)
    setFormError(null)
    try {
      await register({ name: name.trim(), email: email.trim(), password })
      // PublicOnly redirects once the session is set
    } catch (error) {
      setFormError(errorMessage(error))
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Upload a dataset and ask your first question in a few minutes."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="text-brand-text font-medium underline-offset-4 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} noValidate className="flex flex-col gap-4">
        <FormError message={formError} />
        <Field label="Name" error={errors.name}>
          {(p) => <Input {...p} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label="Work email" error={errors.email}>
          {(p) => (
            <Input {...p} type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          )}
        </Field>
        <Field label="Password" hint="At least 8 characters." error={errors.password}>
          {(p) => (
            <Input
              {...p}
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" size="lg" disabled={pending} className="mt-2 w-full">
          {pending ? 'Creating account' : 'Start analyzing'}
        </Button>
      </form>
    </AuthLayout>
  )
}
