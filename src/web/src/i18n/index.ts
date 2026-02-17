import en from './locales/en.json';
import es from './locales/es.json';
import fr from './locales/fr.json';
import de from './locales/de.json';
import pt from './locales/pt.json';
import ja from './locales/ja.json';
import ko from './locales/ko.json';
import zh from './locales/zh.json';

export const locales = { en, es, fr, de, pt, ja, ko, zh } as const;

export type Locale = keyof typeof locales;

export const LOCALE_NAMES: Record<Locale, string> = {
  en: 'English',
  es: 'Español',
  fr: 'Français',
  de: 'Deutsch',
  pt: 'Português',
  ja: '日本語',
  ko: '한국어',
  zh: '中文',
};

export const DEFAULT_LOCALE: Locale = 'en';

type TranslationValue = string | Record<string, unknown>;

// Flatten nested keys: { common: { signIn: "x" } } => "common.signIn"
function flattenMessages(obj: Record<string, unknown>, prefix = ''): Record<string, string> {
  const result: Record<string, string> = {};
  for (const key of Object.keys(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    const value = obj[key] as TranslationValue;
    if (typeof value === 'string') {
      result[fullKey] = value;
    } else if (typeof value === 'object' && value !== null) {
      Object.assign(result, flattenMessages(value as Record<string, unknown>, fullKey));
    }
  }
  return result;
}

// Pre-flatten all locales for fast lookup
const flatLocales: Record<Locale, Record<string, string>> = {} as Record<Locale, Record<string, string>>;
for (const [locale, messages] of Object.entries(locales)) {
  flatLocales[locale as Locale] = flattenMessages(messages as Record<string, unknown>);
}

export function getTranslation(locale: Locale, key: string): string {
  return flatLocales[locale]?.[key] ?? flatLocales[DEFAULT_LOCALE]?.[key] ?? key;
}

export { flatLocales };
