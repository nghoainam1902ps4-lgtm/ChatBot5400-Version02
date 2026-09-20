import { enUS } from './en-US';
import { viVN } from './vi-VN';

export const resources = {
  'vi-VN': { translation: viVN },
  'en-US': { translation: enUS },
} as const;

export type TranslationKeys = typeof enUS;

export type LanguageCode = keyof typeof resources;

export type Language = {
  code: LanguageCode;
  label: string;
};

export const languages: Language[] = [
  { code: 'vi-VN', label: 'Tiếng Việt' },
  { code: 'en-US', label: 'English' },
];

export { enUS, viVN };
