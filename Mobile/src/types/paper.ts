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
  relevance_score?: number | null
  is_large_institution?: boolean
  abstract?: string
  images?: string[]
  image_count?: number
}

export interface AssetBlock {
  text: string
  bullets: string[]
}

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

export interface DatesResponse {
  dates: string[]
}

export interface PapersResponse {
  date: string
  count: number
  papers: PaperSummary[]
  total_available?: number
  quota_limit?: number | null
  tier?: UserTier | 'anonymous'
}

export interface PaperDetailResponse {
  summary: PaperSummary
  paper_assets: PaperAssets | null
  date: string
  images: string[]
  arxiv_url: string
  pdf_url: string
}

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

// ---------------------------------------------------------------------------
// Knowledge Base types
// ---------------------------------------------------------------------------

export interface KbPaper {
  id: number
  paper_id: string
  folder_id: number | null
  paper_data: PaperSummary
  created_at: string
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

export interface KbFolder {
  id: number
  name: string
  parent_id: number | null
  children: KbFolder[]
  papers: KbPaper[]
  created_at: string
  updated_at: string
}

export interface KbTree {
  folders: KbFolder[]
  papers: KbPaper[]
}

/** Context menu / action sheet item */
export interface KbMenuItem {
  key: string
  label: string
  danger?: boolean
}

// ---------------------------------------------------------------------------
// Compare types
// ---------------------------------------------------------------------------

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
  results: KbCompareResult[]
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

// ---------------------------------------------------------------------------
// Idea types (灵感生成 v2)
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
  evidence: { text: string; location: string; snippet?: string; page?: number; paragraph?: number }[]
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
  evidence: { text: string; location: string; snippet?: string; page?: number; paragraph?: number }[]
  risks: string
  scores: IdeaCandidateScores
  status: 'draft' | 'review' | 'approved' | 'archived' | 'implemented'
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
  timestamp?: string
  reviewer_role?: string
  content_diff?: string
  [key: string]: any
}

/** Execution / experiment plan linked to a candidate */
export interface IdeaPlan {
  id: number
  user_id: number
  candidate_id: number
  milestones: { name: string; status: string }[]
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

/** Evaluation benchmark */
export interface IdeaBenchmark {
  id: number
  user_id: number
  name: string
  description?: string
  question_ids: number[]
  model_version: string
  results: Record<string, any>
  created_at: string
  updated_at: string
}

// -- API Response types ---

export interface IdeaStatsResponse {
  ok: boolean
  stats: {
    total_atoms: number
    total_candidates: number
    total_approved: number
    total_archived: number
    total_plans: number
    total_exemplars: number
    total_benchmarks: number
    atoms_by_type: Record<string, number>
    candidates_by_status: Record<string, number>
  }
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

export interface IdeaCandidatesResponse {
  ok: boolean
  candidates: IdeaCandidate[]
  count?: number
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

export interface IdeaBenchmarksResponse {
  ok: boolean
  benchmarks: IdeaBenchmark[]
}

export interface IdeaDigestResponse {
  ok: boolean
  candidates: IdeaCandidate[]
  total_available: number
  quota_limit: number | null
  tier: string
}
