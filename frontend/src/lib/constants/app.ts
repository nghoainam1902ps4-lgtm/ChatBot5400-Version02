import packageJson from '../../../package.json'

/**
 * Internal branding and version configuration.
 * The version is read from frontend/package.json at build time, so it always
 * matches the released version of this repository (see the root VERSION file).
 */
export const APP_NAME = 'AGRIBANK CHI NHÁNH LÂM ĐỒNG'
export const APP_VERSION: string = packageJson.version
