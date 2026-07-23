/** Injected at build time from package.json (vite define). */
export const appVersion = import.meta.env.PACKAGE_VERSION || '0.0.0'

/** Optional short git commit from BUILD_COMMIT env at build time. */
export const buildCommit = import.meta.env.BUILD_COMMIT || ''

export function formatAppVersion ({ includeCommit = true } = {}) {
  const base = `v${appVersion}`
  if (includeCommit && buildCommit) {
    return `${base} · ${buildCommit}`
  }

  return base
}
