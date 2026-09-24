import { APP_LATEST_RELEASE_API } from '@/lib/constants/app'

interface ParsedVersion {
  core: number[]
  prerelease: string[]
}

/**
 * Normalize a version or release tag: trims, drops a leading "v"/"V" and any
 * separator right after it ("v0.0.3", "v.0.0.2", "V 1.2" -> "0.0.3", ...),
 * and strips build metadata ("+build.5").
 */
export function normalizeVersion(raw: string): string {
  return raw
    .trim()
    .replace(/^[vV][\s.\-_]*/, '')
    .split('+')[0]
}

function parseVersion(raw: string): ParsedVersion | null {
  const normalized = normalizeVersion(raw)
  const match = /^(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.-]+))?$/.exec(normalized)
  if (!match) return null
  return {
    core: match[1].split('.').map(Number),
    prerelease: match[2] ? match[2].split('.') : [],
  }
}

function comparePrerelease(a: string[], b: string[]): number {
  // A version without pre-release ranks higher: 1.0.0-rc.1 < 1.0.0
  if (a.length === 0 && b.length === 0) return 0
  if (a.length === 0) return 1
  if (b.length === 0) return -1

  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if (a[i] === undefined) return -1
    if (b[i] === undefined) return 1
    const aNum = /^\d+$/.test(a[i])
    const bNum = /^\d+$/.test(b[i])
    if (aNum && bNum) {
      const diff = Number(a[i]) - Number(b[i])
      if (diff !== 0) return Math.sign(diff)
    } else if (aNum !== bNum) {
      // Numeric identifiers rank lower than alphanumeric ones
      return aNum ? -1 : 1
    } else if (a[i] !== b[i]) {
      return a[i] < b[i] ? -1 : 1
    }
  }
  return 0
}

/**
 * Compare two versions following SemVer precedence.
 * Missing numeric parts count as 0 ("1.2" == "1.2.0") and each part is
 * compared as a number ("0.0.10" > "0.0.9").
 *
 * @returns -1 if a < b, 0 if equal, 1 if a > b
 * @throws Error if either version cannot be parsed
 */
export function compareVersions(a: string, b: string): -1 | 0 | 1 {
  const va = parseVersion(a)
  const vb = parseVersion(b)
  if (!va || !vb) {
    throw new Error(`Invalid version: ${!va ? a : b}`)
  }

  for (let i = 0; i < Math.max(va.core.length, vb.core.length); i++) {
    const diff = (va.core[i] ?? 0) - (vb.core[i] ?? 0)
    if (diff !== 0) return diff > 0 ? 1 : -1
  }
  return comparePrerelease(va.prerelease, vb.prerelease) as -1 | 0 | 1
}

/**
 * Fetch the latest published release version from GitHub.
 * Returns the tag_name without its "v" prefix (e.g. "v0.0.3" -> "0.0.3").
 * Throws on network errors, timeouts, non-2xx responses or a missing tag.
 */
export async function fetchLatestVersion(timeoutMs = 10000): Promise<string> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(APP_LATEST_RELEASE_API, {
      headers: { Accept: 'application/vnd.github+json' },
      cache: 'no-store',
      signal: controller.signal,
    })
    if (!response.ok) {
      throw new Error(`GitHub API returned status ${response.status}`)
    }
    const data: { tag_name?: unknown } = await response.json()
    if (typeof data.tag_name !== 'string' || !data.tag_name.trim()) {
      throw new Error('GitHub release has no tag_name')
    }
    return normalizeVersion(data.tag_name)
  } finally {
    clearTimeout(timer)
  }
}
