import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import fr from './locales/fr.json';
import en from './locales/en.json';

/** The languages the interface is available in. */
export const LANGUAGES = [
  { code: 'fr', label: 'Français' },
  { code: 'en', label: 'English' },
] as const;

/** Where the chosen language is remembered between visits. */
const STORAGE_KEY = 'rt-erp.language';

/**
 * Read the language to start in.
 *
 * @returns The stored language, or French.
 *
 * @remarks
 * French is the default rather than the browser's language: this is a French
 * home-care agency, its contract types and its holidays are French, and an
 * operator whose laptop happens to be in English should still land on the
 * language their colleagues use.
 */
function initialLanguage(): string {
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored && LANGUAGES.some((entry) => entry.code === stored) ? stored : 'fr';
}

void i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr }, en: { translation: en } },
  lng: initialLanguage(),
  fallbackLng: 'fr',
  interpolation: { escapeValue: false },
});

/**
 * Switch the interface language and remember the choice.
 *
 * @param code - The language to switch to.
 */
export function setLanguage(code: string): void {
  window.localStorage.setItem(STORAGE_KEY, code);
  void i18n.changeLanguage(code);
}

export default i18n;
