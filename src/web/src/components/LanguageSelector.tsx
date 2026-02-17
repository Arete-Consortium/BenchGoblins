'use client';

import { useState, useRef, useEffect } from 'react';
import { Globe } from 'lucide-react';
import { type Locale, LOCALE_NAMES } from '@/i18n';
import { useTranslation } from '@/i18n/I18nProvider';

const localeEntries = Object.entries(LOCALE_NAMES) as [Locale, string][];

export function LanguageSelector() {
  const { locale, setLocale } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm text-dark-300 hover:text-dark-100 hover:bg-dark-800 transition-colors"
        aria-label="Select language"
      >
        <Globe className="h-4 w-4" />
        <span className="hidden sm:inline">{LOCALE_NAMES[locale]}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-44 rounded-lg bg-dark-800 border border-dark-700 shadow-xl z-50 py-1 overflow-hidden">
          {localeEntries.map(([code, name]) => (
            <button
              key={code}
              onClick={() => {
                setLocale(code);
                setOpen(false);
              }}
              className={`w-full text-left px-4 py-2 text-sm transition-colors ${
                code === locale
                  ? 'bg-primary-600/20 text-primary-400'
                  : 'text-dark-300 hover:bg-dark-700 hover:text-dark-100'
              }`}
            >
              {name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default LanguageSelector;
