import en from './en.json'
import kn from './kn.json'
import hi from './hi.json'

export const LANGUAGES = [
  { value: 'en-IN', label: 'English' },
  { value: 'kn-IN', label: 'ಕನ್ನಡ' },
  { value: 'hi-IN', label: 'हिन्दी' }
] as const

export type Language = (typeof LANGUAGES)[number]['value']
export type Translator = (key: string, vars?: { count?: number } & Record<string, string | number>) => string

const catalogues: Record<Language, Record<string, string>> = {
  'en-IN': en,
  'kn-IN': kn,
  'hi-IN': hi
}

export function normalizeLanguage(value: string | null | undefined): Language {
  const language = value?.split('-', 1)[0].toLowerCase()
  if (language === 'kn') return 'kn-IN'
  if (language === 'hi') return 'hi-IN'
  return 'en-IN'
}

function createTranslator(language: Language): Translator {
  const catalogue = catalogues[language]
  return (key, vars) => {
    const pluralKey = vars?.count === undefined ? undefined : `${key}_${vars.count === 1 ? 'one' : 'other'}`
    const template = (pluralKey ? catalogue[pluralKey] : undefined) ?? catalogue[key] ?? key
    return template.replace(/\{([^}]+)\}/g, (placeholder, name: string) =>
      vars && Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : placeholder
    )
  }
}

const translators: Record<Language, Translator> = {
  'en-IN': createTranslator('en-IN'),
  'kn-IN': createTranslator('kn-IN'),
  'hi-IN': createTranslator('hi-IN')
}

export function translator(language: string | null | undefined): Translator {
  return translators[normalizeLanguage(language)]
}
