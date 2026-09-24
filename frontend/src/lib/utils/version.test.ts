import { afterEach, describe, expect, it, vi } from 'vitest'
import { compareVersions, fetchLatestVersion, normalizeVersion } from './version'

describe('normalizeVersion', () => {
  it('strips the v prefix, stray separators and build metadata', () => {
    expect(normalizeVersion('v0.0.3')).toBe('0.0.3')
    expect(normalizeVersion('v.0.0.2')).toBe('0.0.2')
    expect(normalizeVersion(' V1.2.0+build.7 ')).toBe('1.2.0')
    expect(normalizeVersion('0.0.3')).toBe('0.0.3')
  })
})

describe('compareVersions', () => {
  it('detects a newer release', () => {
    expect(compareVersions('0.0.3', '0.0.2')).toBe(1)
    expect(compareVersions('0.0.2', '0.0.3')).toBe(-1)
  })

  it('compares parts numerically, not as strings', () => {
    expect(compareVersions('0.0.10', '0.0.9')).toBe(1)
    expect(compareVersions('0.10.0', '0.9.9')).toBe(1)
    expect(compareVersions('2.0.0', '10.0.0')).toBe(-1)
  })

  it('treats missing parts as zero and ignores the v prefix', () => {
    expect(compareVersions('1.2', '1.2.0')).toBe(0)
    expect(compareVersions('v0.0.3', '0.0.3')).toBe(0)
    expect(compareVersions('v.0.0.2', '0.0.3')).toBe(-1)
  })

  it('follows SemVer pre-release precedence', () => {
    expect(compareVersions('1.0.0-rc.1', '1.0.0')).toBe(-1)
    expect(compareVersions('1.0.0-alpha', '1.0.0-beta')).toBe(-1)
    expect(compareVersions('1.0.0-rc.2', '1.0.0-rc.10')).toBe(-1)
    expect(compareVersions('1.0.0-alpha.1', '1.0.0-alpha')).toBe(1)
  })

  it('throws on unparseable input', () => {
    expect(() => compareVersions('latest', '1.0.0')).toThrow()
  })
})

describe('fetchLatestVersion', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns tag_name without the v prefix', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ tag_name: 'v0.0.3' }),
    }))
    await expect(fetchLatestVersion()).resolves.toBe('0.0.3')
  })

  it('throws on a non-2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({}) }))
    await expect(fetchLatestVersion()).rejects.toThrow('403')
  })

  it('throws on network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(fetchLatestVersion()).rejects.toThrow('Failed to fetch')
  })
})
