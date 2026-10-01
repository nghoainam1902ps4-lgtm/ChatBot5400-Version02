import { MessageSquare, Code, Mic, Volume2, Box } from 'lucide-react'

// Provider metadata (names, display names, modalities, docs links) comes
// from the backend registry via GET /api/providers — see useProviders()
// (src/lib/hooks/use-providers.ts). Only genuinely presentational data
// lives here: how each model modality is rendered (icon, color, label).
//
// Modalities arrive as runtime strings from the API, so every lookup has
// a fallback: an unknown modality still renders (generic icon, raw name)
// instead of breaking. Adding a provider must never require a frontend
// edit.

export type ModelType = 'language' | 'embedding' | 'text_to_speech' | 'speech_to_text'

export const MODEL_TYPES: ModelType[] = [
  'language',
  'embedding',
  'text_to_speech',
  'speech_to_text',
]

const TYPE_ICONS: Record<ModelType, React.ReactNode> = {
  language: <MessageSquare className="h-3 w-3" />,
  embedding: <Code className="h-3 w-3" />,
  text_to_speech: <Volume2 className="h-3 w-3" />,
  speech_to_text: <Mic className="h-3 w-3" />,
}

// Mandatory fallback for modality strings the frontend doesn't know yet.
const FALLBACK_TYPE_ICON: React.ReactNode = <Box className="h-3 w-3" />

const TYPE_COLORS: Record<ModelType, string> = {
  language: 'bg-teal-tint text-teal',
  embedding: 'bg-plum-tint text-plum',
  text_to_speech: 'bg-gold-tint text-gold',
  speech_to_text: 'bg-sage-tint text-sage',
}

export const TYPE_COLOR_INACTIVE = 'bg-muted text-muted-foreground opacity-50'

const TYPE_COLOR_FALLBACK = 'bg-muted text-muted-foreground'

// Legacy English labels: used when no translator is passed (e.g. callers
// outside the P1B surfaces such as DiscoverModelsDialog).
const TYPE_LABELS: Record<ModelType, string> = {
  language: 'Language',
  embedding: 'Embedding',
  text_to_speech: 'TTS',
  speech_to_text: 'STT',
}

const TYPE_LABEL_KEYS: Record<ModelType, string> = {
  language: 'models.type.language',
  embedding: 'models.type.embedding',
  text_to_speech: 'models.type.textToSpeech',
  speech_to_text: 'models.type.speechToText',
}

export function getTypeIcon(type: string): React.ReactNode {
  return TYPE_ICONS[type as ModelType] ?? FALLBACK_TYPE_ICON
}

export function getTypeColor(type: string): string {
  return TYPE_COLORS[type as ModelType] ?? TYPE_COLOR_FALLBACK
}

/**
 * Label for a modality. With a translator, known modalities are localized;
 * an unknown modality always falls back to its raw name (never a raw i18n
 * key), so a new backend modality needs no frontend edit.
 */
export function getTypeLabel(type: string, t?: (key: string) => string): string {
  if (!Object.prototype.hasOwnProperty.call(TYPE_LABELS, type)) return type
  const known = type as ModelType
  return t ? t(TYPE_LABEL_KEYS[known]) : TYPE_LABELS[known]
}
