import { createI18n } from 'vue-i18n'
import en from './locales/en.js'
import zh from './locales/zh.js'

// Single source of truth for BOTH interface chrome and LLM-generated content
// language is goals.explanation_language (B-RC2-8) — there is no separate
// "UI language" setting. i18n.global.locale is kept in sync with the active
// goal's explanation_language by the store/App shell, not chosen independently.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en, zh }
})

export default i18n
