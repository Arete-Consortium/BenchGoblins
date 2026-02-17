'use client';

import { createContext, useContext, useCallback } from 'react';
import { type Locale, DEFAULT_LOCALE, getTranslation } from './index';
import { usePreferencesStore } from '@/stores/preferences';

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue>({
  locale: DEFAULT_LOCALE,
  setLocale: () => {},
  t: (key: string) => key,
});

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const locale = usePreferencesStore((s) => s.language);
  const setLocale = usePreferencesStore((s) => s.setLanguage);

  const t = useCallback(
    (key: string) => getTranslation(locale, key),
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useTranslation() {
  return useContext(I18nContext);
}
