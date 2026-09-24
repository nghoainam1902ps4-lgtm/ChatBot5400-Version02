import packageJson from '../../../package.json'

/**
 * Internal branding and version configuration.
 * The version is read from frontend/package.json at build time, so it always
 * matches the released version of this repository (see the root VERSION file).
 */
export const APP_NAME = 'AGRIBANK CHI NHÁNH LÂM ĐỒNG'
export const APP_VERSION: string = packageJson.version

/** GitHub repository whose releases are used for the update check. */
export const APP_GITHUB_REPO = 'nghoainam1902ps4-lgtm/ChatBot5400-Version02'
export const APP_LATEST_RELEASE_API = `https://api.github.com/repos/${APP_GITHUB_REPO}/releases/latest`
