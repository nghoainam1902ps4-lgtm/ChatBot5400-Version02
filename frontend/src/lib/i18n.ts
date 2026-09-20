import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { resources } from './locales'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    // First open defaults to Vietnamese; after login each user's saved language
    // is applied (see auth-store). English is the fallback for any missing key.
    lng: 'vi-VN',
    fallbackLng: 'en-US',
    supportedLngs: ['vi-VN', 'en-US'],
    interpolation: {
      escapeValue: false, // react already safes from xss
    },
    react: {
      useSuspense: false,
    },
    detection: {
      // Only trust an explicit prior choice (localStorage); do NOT infer from
      // the browser's navigator language, so the default stays Vietnamese.
      order: ['localStorage'],
      caches: ['localStorage'],
    },
  })

export default i18n
