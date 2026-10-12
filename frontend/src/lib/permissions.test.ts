import { describe, expect, it } from 'vitest'
import { testUser } from '@/test/utils'
import { roleAbilities, sourceAbilities } from './permissions'

describe('role abilities', () => {
  it('viewers cannot create anything, analysts and admins can', () => {
    expect(roleAbilities(testUser({ role: 'viewer' })).canCreate).toBe(false)
    expect(roleAbilities(testUser({ role: 'analyst' })).canCreate).toBe(true)
    expect(roleAbilities(testUser({ role: 'admin', is_admin: true }))).toMatchObject({ isAdmin: true, canCreate: true })
  })
})

describe('source abilities', () => {
  const analyst = testUser({ role: 'analyst' })
  it('owners manage and ask', () => {
    expect(sourceAbilities({ access: 'manage', owned: true }, analyst)).toMatchObject({
      canManage: true,
      canAsk: true,
      shared: false,
    })
  })
  it('an analyst share can ask but not manage', () => {
    expect(sourceAbilities({ access: 'ask', owned: false }, analyst)).toMatchObject({
      canManage: false,
      canAsk: true,
      shared: true,
    })
  })
  it('a read share can neither ask nor manage', () => {
    expect(sourceAbilities({ access: 'read', owned: false }, analyst)).toMatchObject({
      canManage: false,
      canAsk: false,
    })
  })
  it('a viewer never asks, even with ask access', () => {
    expect(sourceAbilities({ access: 'ask', owned: false }, testUser({ role: 'viewer' })).canAsk).toBe(false)
  })
  it('upload responses without access are the caller own source', () => {
    expect(sourceAbilities({ access: null, owned: true }, analyst).canManage).toBe(true)
  })
})
