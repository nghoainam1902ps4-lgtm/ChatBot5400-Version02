export interface NotebookResponse {
  id: string
  name: string
  description: string
  archived: boolean
  created: string
  updated: string
  source_count: number
  note_count: number
  // Hierarchy / approval scope (ChatBot5400)
  parent?: string | null
  managers?: string[]
  is_category?: boolean
}

export interface NoteResponse {
  id: string
  title: string | null
  content: string | null
  note_type: string | null
  created: string
  updated: string
}

export interface SourceListResponse {
  id: string
  title: string | null
  topics?: string[]                  // Make optional to match Python API
  asset: {
    file_path?: string
    url?: string
  } | null
  embedded: boolean
  embedded_chunks: number            // ADD: From Python API
  insights_count: number
  created: string
  updated: string
  file_available?: boolean
  // ADD: Async processing fields from Python API
  command_id?: string
  status?: string
  processing_info?: Record<string, unknown>
  // Approval workflow (ChatBot5400): approved | pending | rejected
  approval_status?: string
}

export interface SourceDetailResponse extends SourceListResponse {
  full_text: string
  notebooks?: string[]  // List of notebook IDs this source is linked to
  submitted_by?: string | null
  review_note?: string | null
}

export type SourceResponse = SourceDetailResponse

export interface SourceStatusResponse {
  status?: string
  message: string
  processing_info?: Record<string, unknown>
  command_id?: string
}

export interface SettingsResponse {
  default_content_processing_engine_doc?: string
  default_content_processing_engine_url?: string
  default_embedding_option?: string
  auto_delete_files?: string
  docling_ocr?: boolean
  docling_formulas?: boolean
  docling_vision?: boolean
  youtube_preferred_languages?: string[]
  podcast_enabled?: boolean
  /** Read-only here; changed via POST /ocr/engines/{id}/activate. */
  docling_ocr_engine?: string
}

export interface Capabilities {
  docling_available: boolean
  crawl4ai_available: boolean
  crawl4ai_remote_configured: boolean
}

export interface CreateNotebookRequest {
  name: string
  description?: string
  // Set parent to create a sub-notebook under a category (approver/admin).
  parent?: string | null
  // Admin-only: approver user ids assigned to manage this category.
  managers?: string[]
}

export interface UpdateNotebookRequest {
  name?: string
  description?: string
  archived?: boolean
  // Admin-only: reassign which approvers manage this category.
  managers?: string[]
}

export interface NotebookDeletePreview {
  notebook_id: string
  notebook_name: string
  note_count: number
  exclusive_source_count: number
  shared_source_count: number
}

export interface NotebookDeleteResponse {
  message: string
  deleted_notes: number
  deleted_sources: number
  unlinked_sources: number
}

export interface CreateNoteRequest {
  title?: string
  content: string
  note_type?: string
  notebook_id?: string
}

export interface CreateSourceRequest {
  // Backward compatibility: support old single notebook_id
  notebook_id?: string
  // New multi-notebook support
  notebooks?: string[]
  // Required fields
  type: 'link' | 'upload' | 'text'
  url?: string
  file_path?: string
  content?: string
  title?: string
  transformations?: string[]
  embed?: boolean
  delete_source?: boolean
  // New async processing support
  async_processing?: boolean
  // Directed approval: the approver (Kiểm soát) to route a submission to.
  reviewer_id?: string
}

export interface UpdateNoteRequest {
  title?: string
  content?: string
  note_type?: string
}

export interface UpdateSourceRequest {
  title?: string
  type?: 'link' | 'upload' | 'text'
  url?: string
  content?: string
}

export interface APIError {
  detail: string
}

// Source Chat Types
// Base session interface with common fields
export interface BaseChatSession {
  id: string
  title: string
  created: string
  updated: string
  message_count?: number
  model_override?: string | null
}

export interface SourceChatSession extends BaseChatSession {
  source_id: string
  model_override?: string
}

export interface SourceChatMessage {
  id: string
  type: 'human' | 'ai'
  content: string
  timestamp?: string
}

export interface SourceChatContextIndicator {
  sources: string[]
  insights: string[]
  notes: string[]
}

export interface SourceChatSessionWithMessages extends SourceChatSession {
  messages: SourceChatMessage[]
  context_indicators?: SourceChatContextIndicator
}

export interface CreateSourceChatSessionRequest {
  source_id: string
  title?: string
  model_override?: string
}

export interface UpdateSourceChatSessionRequest {
  title?: string
  model_override?: string
}

export interface SendMessageRequest {
  message: string
  model_override?: string
}

export interface SourceChatStreamEvent {
  type: 'user_message' | 'ai_message' | 'context_indicators' | 'complete' | 'error'
  content?: string
  data?: unknown
  message?: string
  timestamp?: string
}

// Notebook Chat Types
export interface NotebookChatSession extends BaseChatSession {
  notebook_id: string
}

export interface NotebookChatMessage {
  id: string
  type: 'human' | 'ai'
  content: string
  timestamp?: string
}

export interface NotebookChatSessionWithMessages extends NotebookChatSession {
  messages: NotebookChatMessage[]
}

export interface CreateNotebookChatSessionRequest {
  notebook_id: string
  title?: string
  model_override?: string
}

export interface UpdateNotebookChatSessionRequest {
  title?: string
  model_override?: string | null
}

export interface SendNotebookChatMessageRequest {
  session_id: string
  message: string
  context: {
    sources: Array<Record<string, unknown>>
    notes: Array<Record<string, unknown>>
  }
  model_override?: string
}

export interface BuildContextRequest {
  notebook_id: string
  context_config: {
    sources: Record<string, string>
    notes: Record<string, string>
  }
}

export interface BuildContextResponse {
  context: {
    sources: Array<Record<string, unknown>>
    notes: Array<Record<string, unknown>>
  }
  token_count: number
  char_count: number
}

export interface RecentlyViewedResponse {
  type: 'notebook' | 'source'
  id: string
  title: string
  last_viewed_at: string
}

// AI Feedback (P2A)
export type FeedbackReaction = 'like' | 'dislike' | null

export interface FeedbackState {
  message_id: string
  reaction: FeedbackReaction
  reported: boolean
}

export interface SetReactionRequest {
  session_id: string
  reaction: FeedbackReaction
}

export interface ReportMessageRequest {
  session_id: string
  reason: string
}

export interface AdminFeedbackStats {
  total: number
  likes: number
  dislikes: number
  reports: number
}

export interface AdminFeedbackItem {
  id: string
  username_snapshot: string
  user_name_snapshot: string | null
  session_id: string
  message_id: string
  context_type: 'notebook' | 'source'
  context_id: string | null
  context_title_snapshot: string | null
  question_snapshot: string
  answer_snapshot: string
  reaction: FeedbackReaction
  reported: boolean
  report_reason: string | null
  reported_at: string | null
  created: string | null
  updated: string | null
}

export interface AdminFeedbackListResponse {
  items: AdminFeedbackItem[]
  page: number
  page_size: number
  total: number
  total_pages: number
}

export interface AdminFeedbackListParams {
  page?: number
  page_size?: number
  q?: string
  type?: 'like' | 'dislike' | 'report'
  context?: 'notebook' | 'source'
  sort?: string
  direction?: 'asc' | 'desc'
}

// OCR Engine Manager (docs/ocr/OCR_ENGINE_MANAGER.md)
export type OcrEngineId = 'rapidocr' | 'tesseract_fast' | 'tesseract_best' | 'easyocr'

export type OcrLifecycleState =
  | 'not_installed'
  | 'pending'
  | 'downloading'
  | 'installing'
  | 'requires_restart'
  | 'ready'
  | 'failed'
  | 'incompatible'

export interface OcrRuntimeStatus {
  kind: string
  status: 'ready' | 'missing' | 'incompatible' | 'requires_restart'
  version?: string | null
  detail?: string | null
  install_env_var?: string | null
  install_cli?: string | null
  extra?: Record<string, unknown>
}

export interface OcrTestResult {
  engine: string
  display_name?: string
  model?: string
  languages?: string[]
  device?: string
  docling_class?: string
  ocr_models?: string[]
  text?: string
  cer?: number
  success: boolean
  error?: string
  elapsed_seconds?: number
  tested_at?: number
}

export interface OcrEngineStatus {
  id: OcrEngineId
  display_name: string
  description: string
  languages: string[]
  model_name: string
  model_version: string
  license: string
  source_url: string
  builtin: boolean
  download_size_bytes: number
  size_bytes: number
  installed_size_bytes: number
  runtime: OcrRuntimeStatus
  model: { status: string; installed_bytes: number; files: { rel_path: string; present: boolean; verified: boolean }[] }
  state: OcrLifecycleState
  ready: boolean
  active: boolean
  job?: {
    job_id?: string | null
    state?: string | null
    progress?: { bytes_done?: number; bytes_total?: number; file?: string } | null
    updated_at?: number | null
  } | null
  error?: string | null
  smoke?: { ok: boolean | null; detail: string } | null
  last_test?: OcrTestResult | null
  options: Record<string, unknown>
  dependency_problems?: string[]
  readiness?: OcrReadiness
  readiness_job?: 'prepare' | 'check' | null
}

export type OcrReadinessState =
  | 'runtime_missing'
  | 'model_missing'
  | 'model_incomplete'
  | 'incompatible'
  | 'pipeline_not_verified'
  | 'offline_ready'
  | 'not_offline_ready'

export interface OcrReadinessCheck {
  mode: 'online' | 'local_only' | 'offline'
  success?: boolean
  pipeline_ok?: boolean
  checked_at?: number
  error?: string
  layout_model?: string | null
  table_model?: string | null
  table_mode?: string | null
  ocr_models?: string[] | null
}

export interface OcrReadiness {
  state: OcrReadinessState
  ocr_ok: boolean
  pipeline_ok: boolean
  local_only_verified: boolean
  offline_verified: boolean
  stale: boolean
  last_check?: OcrReadinessCheck | null
}

export interface OcrConfig {
  docling_ocr: boolean
  docling_ocr_engine: OcrEngineId
  docling_ocr_device: string
  docling_ocr_num_threads: number | null
  docling_ocr_force_full_page: boolean
}

export interface OcrGeneralInfo {
  document_engine: string
  docling_available: boolean
  docling_version?: string | null
  docling_api_compatible?: boolean | null
  docling_missing_api: string[]
  layout_model?: string | null
  table_model?: string | null
  ocr_device: string
  models_dir: string
  offline_mode: boolean
  dependency_problems?: string[]
  dependency_override?: boolean
}

export interface OcrEnginesResponse {
  general: OcrGeneralInfo
  config: OcrConfig
  engines: OcrEngineStatus[]
}

export interface OcrJobResponse {
  job_id: string
  engine_id: string
  state: string
}

export interface OcrJobStatus {
  job_id: string
  status: string
  result?: { success?: boolean; result?: OcrTestResult; error_message?: string } | null
  error_message?: string | null
}
