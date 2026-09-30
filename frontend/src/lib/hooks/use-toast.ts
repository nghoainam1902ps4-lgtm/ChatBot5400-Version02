import { toast as sonnerToast } from 'sonner'
import { useTranslation } from '@/lib/hooks/use-translation'

/**
 * Runtime notification variants (N2 semantics):
 * - `success`: the operation actually completed.
 * - `error`: the operation failed.
 * - `warn`: needs the user's attention (e.g. partially succeeded).
 * - `info`: neutral, or a job the backend only accepted/queued — never a
 *   completion claim.
 * `default` (→ success) and `destructive` (→ error) are the legacy names, kept
 * so existing callers that are already semantically correct stay unchanged.
 */
export type ToastVariant = 'success' | 'error' | 'warn' | 'info' | 'default' | 'destructive'

type ToastProps = {
  title?: string
  description?: string
  variant?: ToastVariant
}

export function useToast() {
  const { t } = useTranslation()

  return {
    toast: ({ title, description, variant = 'default' }: ToastProps) => {
      switch (variant) {
        case 'error':
        case 'destructive':
          sonnerToast.error(title || t('common.error'), { description })
          break
        case 'warn':
          sonnerToast.warning(title || t('common.warning'), { description })
          break
        case 'info':
          // No generic "info" title exists in the locales; without a title the
          // description itself becomes the message.
          if (title) sonnerToast.info(title, { description })
          else sonnerToast.info(description ?? '')
          break
        case 'success':
        case 'default':
        default:
          sonnerToast.success(title || t('common.success'), { description })
      }
    }
  }
}
