'use client'

import { FormSection } from '@/components/ui/form-section'
import { useTranslation } from '@/lib/hooks/use-translation'
import type { Reviewer } from '@/lib/api/approvals'
import { Loader2 } from 'lucide-react'

interface ReviewerStepProps {
  reviewers: Reviewer[]
  selectedReviewer: string
  onSelect: (reviewerId: string) => void
  loading?: boolean
}

/**
 * Step for a contributor to pick the approver ("Kiểm soát") who will review
 * the submission. When no eligible approver exists for the chosen notebooks,
 * the submission falls back to any approver managing the category.
 */
export function ReviewerStep({
  reviewers,
  selectedReviewer,
  onSelect,
  loading = false,
}: ReviewerStepProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-6">
      <FormSection
        title={t('approvals.chooseReviewer')}
        description={t('approvals.chooseReviewerDesc')}
      >
        {loading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t('common.loading')}
          </div>
        ) : reviewers.length === 0 ? (
          <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
            {t('approvals.noReviewers')}
          </p>
        ) : (
          <div className="space-y-1.5">
            {reviewers.map((r) => (
              <label
                key={r.id}
                className="flex cursor-pointer items-center gap-3 rounded-md border p-3 text-sm hover:bg-muted"
              >
                <input
                  type="radio"
                  name="reviewer"
                  className="h-4 w-4 accent-fern"
                  checked={selectedReviewer === r.id}
                  onChange={() => onSelect(r.id)}
                />
                <span className="flex min-w-0 flex-col">
                  <span className="truncate font-medium">
                    {r.name || r.username}
                  </span>
                  {r.name && (
                    <span className="truncate text-xs text-muted-foreground">
                      {r.username}
                    </span>
                  )}
                </span>
              </label>
            ))}
          </div>
        )}
      </FormSection>
    </div>
  )
}
