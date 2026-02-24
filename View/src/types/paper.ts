/** 单篇论文摘要（来自 file_collect _limit.md + pdf_info.json） */
export interface PaperSummary {
  institution: string
  short_title: string
  '📖标题': string
  '🌐来源': string
  paper_id: string
  '🛎️文章简介': {
    '🔸研究问题': string
    '🔸主要贡献': string
  }
  '📝重点思路': string[]
  '🔎分析总结': string[]
  '💡个人观点': string
  /** Merged from theme scores */
  relevance_score?: number | null
  /** Merged from institution filter / pdf_info.json */
  is_large_institution?: boolean
  /** Paper abstract from pdf_info.json */
  abstract?: string
  /** Image filenames in image/ subdirectory */
  images?: string[]
  /** Number of images */
  image_count?: number
}

/** paper_assets 中的结构化块 */
export interface AssetBlock {
  text: string
  bullets: string[]
}

/** 完整 paper_assets 条目 */
export interface PaperAssets {
  paper_id: string
  title: string
  url: string
  year: number
  blocks: {
    background: AssetBlock
    objective: AssetBlock
    method: AssetBlock
    data: AssetBlock
    experiment: AssetBlock
    metrics: AssetBlock
    results: AssetBlock
    limitations: AssetBlock
  }
}

/** GET /api/dates 响应 */
export interface DatesResponse {
  dates: string[]
}

/** GET /api/papers 响应 */
export interface PapersResponse {
  date: string
  count: number
  papers: PaperSummary[]
  total_available?: number
  quota_limit?: number | null
  tier?: UserTier | 'anonymous'
}

/** GET /api/papers/:id 响应 */
export interface PaperDetailResponse {
  summary: PaperSummary
  paper_assets: PaperAssets | null
  date: string
  images: string[]
  arxiv_url: string
  pdf_url: string
}

/** GET /api/digest/:date 响应 */
export interface DigestResponse {
  date: string
  total_papers: number
  large_institution_count: number
  avg_relevance_score: number | null
  institution_distribution: { name: string; count: number }[]
  papers: PaperSummary[]
  total_available?: number
  quota_limit?: number | null
  tier?: UserTier | 'anonymous'
}

/** Pipeline step status */
export interface PipelineStep {
  step: string
  completed: boolean
}

/** GET /api/pipeline/status 响应 */
export interface PipelineStatusResponse {
  date: string
  steps: PipelineStep[]
}

// ---------------------------------------------------------------------------
// Knowledge Base types
// ---------------------------------------------------------------------------

/** A paper saved in the knowledge base */
export interface KbPaper {
  id: number
  paper_id: string
  folder_id: number | null
  paper_data: PaperSummary
  created_at: string
  /** Number of notes/files attached (populated by tree endpoint) */
  note_count?: number
}

/** A note / file / link attached to a KB paper */
export interface KbNote {
  id: number
  paper_id: string
  type: 'markdown' | 'file' | 'link'
  title: string
  content?: string
  file_path?: string
  file_url?: string
  file_size?: number
  mime_type?: string
  created_at: string
  updated_at: string
}

/** GET /api/kb/papers/:paper_id/notes 响应 */
export interface KbNotesResponse {
  paper_id: string
  notes: KbNote[]
}

/** A PDF annotation (highlight / note) */
export interface KbAnnotation {
  id: number
  paper_id: string
  page: number
  type: 'highlight' | 'text' | 'box'
  content: string
  color: string
  position_data: string
  created_at: string
  updated_at: string
}

/** GET /api/kb/papers/:paper_id/annotations 响应 */
export interface KbAnnotationsResponse {
  paper_id: string
  annotations: KbAnnotation[]
}

/** A folder in the knowledge base (recursive tree) */
export interface KbFolder {
  id: number
  name: string
  parent_id: number | null
  children: KbFolder[]
  papers: KbPaper[]
  created_at: string
  updated_at: string
}

/** GET /api/kb/tree 响应 */
export interface KbTree {
  folders: KbFolder[]
  papers: KbPaper[] // root-level papers (folder_id == null)
}

/** Context menu item */
export interface KbMenuItem {
  key: string
  label: string
  danger?: boolean
}

/** A saved compare analysis result */
export interface KbCompareResult {
  id: number
  title: string
  markdown: string
  paper_ids: string[]
  folder_id: number | null
  created_at: string
  updated_at: string
}

/** A folder in the compare results tree */
export interface KbCompareFolder {
  id: number
  name: string
  parent_id: number | null
  children: KbCompareFolder[]
  results: KbCompareResult[]
  created_at: string
  updated_at: string
}

/** GET /api/kb/compare-results/tree 响应 */
export interface KbCompareResultsTree {
  folders: KbCompareFolder[]
  results: KbCompareResult[] // root-level results
}

// ---------------------------------------------------------------------------
// Auth types
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: number
  username: string
  nickname?: string
  role: UserRole
  tier: UserTier
  phone?: string | null
  phone_verified?: boolean
  is_phone_auto_created?: boolean
  has_password?: boolean
  created_at: string
  updated_at: string
  last_login_at?: string | null
}

export type UserRole = 'user' | 'admin' | 'superadmin'
export type UserTier = 'free' | 'pro' | 'pro_plus'

export interface AuthPayload {
  username: string
  password: string
}

export interface AuthRegisterPayload {
  username: string
  password: string
  phone: string
  sms_code: string
}

export interface AuthSmsLoginPayload {
  phone: string
  code: string
}

export interface SmsSendPayload {
  phone: string
}

export interface SmsSendResponse {
  ok: boolean
  message: string
}

export interface AuthActionResponse {
  ok: boolean
  user: AuthUser
  is_new_user?: boolean
}

export interface AuthMeResponse {
  authenticated: boolean
  user: AuthUser | null
}

export interface AuthLogoutResponse {
  ok: boolean
}

export interface AdminUsersResponse {
  users: AuthUser[]
}

// ---------------------------------------------------------------------------
// Pipeline types
// ---------------------------------------------------------------------------

export interface PipelineRunStatus {
  running: boolean
  current_step: string | null
  logs: string[]
  started_at: string | null
  finished_at: string | null
  exit_code: number | null
  params: {
    pipeline?: string
    date?: string
    sllm?: number | null
    zo?: string
    days?: number | null
    categories?: string | null
    extra_query?: string | null
    max_papers?: number | null
    anchor_tz?: string | null
  }
  /** Run identifier (YYYYMMDD_HHMMSS). Present when disk state is available. */
  run_id?: string | null
}

export interface ScheduleConfig {
  enabled: boolean
  hour: number
  minute: number
  pipeline: string
  sllm: number | null
  zo: string
  user_id?: number | null
  last_run_date?: string | null
}

// ---------------------------------------------------------------------------
// System Config types
// ---------------------------------------------------------------------------

export interface SystemConfigItem {
  key: string
  value: any
  type: string
  description: string
  is_sensitive: boolean
}

export interface SystemConfigGroup {
  name: string
  items: SystemConfigItem[]
}

export interface SystemConfigResponse {
  ok: boolean
  groups: SystemConfigGroup[]
  defaults: Record<string, any>
}

export interface SystemConfigUpdateResponse {
  ok: boolean
  config: Record<string, any>
}

// ---------------------------------------------------------------------------
// LLM Config types
// ---------------------------------------------------------------------------

export interface LlmConfig {
  id: number
  name: string
  remark?: string
  base_url: string
  api_key: string
  model: string
  max_tokens?: number
  temperature?: number
  concurrency?: number
  input_hard_limit?: number
  input_safety_margin?: number
  endpoint?: string
  completion_window?: string
  out_root?: string
  jsonl_root?: string
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// Prompt Config types
// ---------------------------------------------------------------------------

export interface PromptConfig {
  id: number
  name: string
  remark?: string
  prompt_content: string
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// User Preset types
// ---------------------------------------------------------------------------

export interface UserLlmPreset {
  id: number
  user_id: number
  name: string
  base_url: string
  api_key: string
  model: string
  max_tokens?: number | null
  temperature?: number | null
  input_hard_limit?: number | null
  input_safety_margin?: number | null
  created_at: string
  updated_at: string
}

export interface UserPromptPreset {
  id: number
  user_id: number
  name: string
  prompt_content: string
  created_at: string
  updated_at: string
}

// ---------------------------------------------------------------------------
// Inspiration v2 types (灵感生成 v2)
// ---------------------------------------------------------------------------

/** Structured extraction unit from a paper */
export interface IdeaAtom {
  id: number
  user_id: number
  paper_id: string
  date_str: string
  atom_type: 'claim' | 'method' | 'setup' | 'limitation' | 'tag'
  content: string
  tags: string[]
  evidence: { text: string; location: string }[]
  section: string
  source_file: string
  created_at: string
  updated_at: string
}

/** Research question mined from atoms */
export interface IdeaQuestion {
  id: number
  user_id: number
  source_atom_ids: number[]
  question_text: string
  strategy: string
  context: Record<string, any>
  created_at: string
}

/** Inspiration candidate with scores and revision history */
export interface IdeaCandidate {
  id: number
  user_id: number
  question_id: number | null
  title: string
  goal: string
  mechanism: string
  input_atom_ids: number[]
  evidence: { text: string; location: string }[]
  risks: string
  scores: IdeaCandidateScores
  status: 'draft' | 'review' | 'published' | 'archived'
  revision_history: IdeaRevisionEntry[]
  strategy: string
  folder_id: number | null
  tags: string[]
  created_at: string
  updated_at: string
}

export interface IdeaCandidateScores {
  consistency?: number
  novelty?: number
  feasibility?: number
  impact?: number
  overall?: number
  [key: string]: number | undefined
}

export interface IdeaRevisionEntry {
  type: string
  scores?: IdeaCandidateScores
  verdict?: string
  summary?: string
  changes?: Record<string, any>
  [key: string]: any
}

/** Execution / experiment plan linked to a candidate */
export interface IdeaPlan {
  id: number
  user_id: number
  candidate_id: number
  milestones: Record<string, any>[]
  metrics: string
  datasets: string
  ablation: string
  cost: string
  timeline: string
  full_plan: string
  created_at: string
  updated_at: string
}

/** User feedback event on a candidate */
export interface IdeaFeedback {
  id: number
  user_id: number
  candidate_id: number
  action: 'collect' | 'discard' | 'modify' | 'implement' | 'rate' | 'view'
  context: Record<string, any>
  created_at: string
}

/** High-quality inspiration pattern */
export interface IdeaExemplar {
  id: number
  user_id: number
  candidate_id: number | null
  pattern: Record<string, any>
  score: number
  notes: string
  created_at: string
  updated_at: string
}

/** Prompt version record */
export interface IdeaPromptVersion {
  id: number
  user_id: number
  stage: string
  version: number
  prompt_text: string
  metrics: Record<string, any>
  created_at: string
}

/** Evaluation benchmark */
export interface IdeaBenchmark {
  id: number
  user_id: number
  name: string
  question_ids: number[]
  model_version: string
  results: Record<string, any>
  created_at: string
  updated_at: string
}

/** Dashboard statistics */
export interface IdeaStats {
  atom_count: number
  question_count: number
  candidate_count: number
  published_count: number
  exemplar_count: number
  atom_type_distribution: Record<string, number>
}

// -- API Response types ---

export interface IdeaStatsResponse {
  ok: boolean
  atom_count: number
  question_count: number
  candidate_count: number
  published_count: number
  exemplar_count: number
  atom_type_distribution: Record<string, number>
}

export interface IdeaAtomsResponse {
  ok: boolean
  atoms: IdeaAtom[]
  count: number
}

export interface IdeaAtomResponse {
  ok: boolean
  atom: IdeaAtom
}

export interface IdeaQuestionsResponse {
  ok: boolean
  questions: IdeaQuestion[]
  count: number
}

export interface IdeaCandidatesResponse {
  ok: boolean
  candidates: IdeaCandidate[]
  count: number
}

export interface IdeaCandidateResponse {
  ok: boolean
  candidate: IdeaCandidate
}

export interface IdeaPlanResponse {
  ok: boolean
  plan: IdeaPlan
}

export interface IdeaFeedbackResponse {
  ok: boolean
  feedback?: IdeaFeedback
  events?: IdeaFeedback[]
  count?: number
}

export interface IdeaExemplarsResponse {
  ok: boolean
  exemplars: IdeaExemplar[]
}

export interface IdeaPromptVersionsResponse {
  ok: boolean
  versions: IdeaPromptVersion[]
}

export interface IdeaBenchmarksResponse {
  ok: boolean
  benchmarks: IdeaBenchmark[]
}

export interface IdeaLibraryTreeResponse {
  ok: boolean
  folders: KbTree
  candidates: IdeaCandidate[]
}

/** GET /api/idea/digest/:date 响应 */
export interface IdeaDigestResponse {
  ok: boolean
  candidates: IdeaCandidate[]
  total_available: number
  quota_limit: number | null
  tier: string
}