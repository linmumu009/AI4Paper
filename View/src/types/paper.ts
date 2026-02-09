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
