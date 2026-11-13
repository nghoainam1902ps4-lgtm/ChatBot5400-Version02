import apiClient from './client'
import type {
  OcrConfig,
  OcrEngineId,
  OcrEnginesResponse,
  OcrEngineStatus,
  OcrJobResponse,
  OcrJobStatus,
} from '@/lib/types/api'

/** OCR Engine Manager API (admin only; see api/routers/ocr.py). */
export const ocrApi = {
  list: async () => (await apiClient.get<OcrEnginesResponse>('/ocr/engines')).data,
  install: async (id: OcrEngineId) =>
    (await apiClient.post<OcrJobResponse>(`/ocr/engines/${id}/install`)).data,
  activate: async (id: OcrEngineId) =>
    (await apiClient.post<OcrEngineStatus>(`/ocr/engines/${id}/activate`)).data,
  test: async (id: OcrEngineId) =>
    (await apiClient.post<OcrJobResponse>(`/ocr/engines/${id}/test`)).data,
  prepare: async (id: OcrEngineId) =>
    (await apiClient.post<OcrJobResponse>(`/ocr/engines/${id}/prepare`)).data,
  readinessCheck: async (id: OcrEngineId) =>
    (await apiClient.post<OcrJobResponse>(`/ocr/engines/${id}/readiness-check`)).data,
  removeModel: async (id: OcrEngineId) =>
    (await apiClient.delete<{ engine_id: string; removed: string[] }>(`/ocr/engines/${id}/model`)).data,
  job: async (jobId: string) =>
    (await apiClient.get<OcrJobStatus>(`/ocr/jobs/${encodeURIComponent(jobId)}`)).data,
  updateConfig: async (data: Partial<Pick<OcrConfig, 'docling_ocr' | 'docling_ocr_force_full_page'>> & {
    docling_ocr_num_threads?: number
  }) => (await apiClient.put<OcrConfig>('/ocr/config', data)).data,
}
