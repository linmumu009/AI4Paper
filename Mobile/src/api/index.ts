import axios from 'axios'
import type {
  DatesResponse,
  PaperDetailResponse,
  DigestResponse,
  KbTree,
  KbFolder,
  KbPaper,
  KbNote,
  KbNotesResponse,
  KbCompareResult,
  KbCompareResultsTree,
  PaperSummary,
  AuthPayload,
  AuthRegisterPayload,
  AuthSmsLoginPayload,
  SmsSendPayload,
  SmsSendResponse,
  AuthActionResponse,
  AuthMeResponse,
  AuthLogoutResponse,
  IdeaAtom,
  IdeaCandidate,
  IdeaPlan,
  IdeaExemplar,
  IdeaBenchmark,
  IdeaStatsResponse,
  IdeaAtomsResponse,
  IdeaAtomResponse,
  IdeaCandidatesResponse,
  IdeaCandidateResponse,
  IdeaPlanResponse,
  IdeaFeedbackResponse,
  IdeaExemplarsResponse,
  IdeaBenchmarksResponse,
  IdeaDigestResponse,
} from '../types/paper'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true,
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status
    const url: string = error?.config?.url || ''
    const isKbEndpoint = url.startsWith('/kb') || url.includes('/kb/')
    if (status === 401 && isKbEndpoint) {
      window.dispatchEvent(new CustomEvent('auth-required'))
    }
    return Promise.reject(error)
  },
)

// ---------------------------------------------------------------------------
// Dates & Papers
// ---------------------------------------------------------------------------

export async function fetchDates(): Promise<DatesResponse> {
  const { data } = await http.get<DatesResponse>('/dates')
  return data
}

export async function fetchDigest(date: string): Promise<DigestResponse> {
  const { data } = await http.get<DigestResponse>(`/digest/${date}`)
  return data
}

export async function fetchPaperDetail(paperId: string): Promise<PaperDetailResponse> {
  const { data } = await http.get<PaperDetailResponse>(`/papers/${paperId}`)
  return data
}

// ---------------------------------------------------------------------------
// Knowledge Base
// ---------------------------------------------------------------------------

export type KbScope = 'kb' | 'inspiration'

export async function fetchKbTree(scope: KbScope = 'kb'): Promise<KbTree> {
  const { data } = await http.get<KbTree>('/kb/tree', { params: { scope } })
  return data
}

export async function createKbFolder(name: string, parentId?: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.post<KbFolder>('/kb/folders', {
    name,
    parent_id: parentId ?? null,
    scope,
  })
  return data
}

export async function renameKbFolder(folderId: number, name: string, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}`, { name, scope })
  return data
}

export async function moveKbFolder(folderId: number, targetParentId: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}/move`, {
    target_parent_id: targetParentId,
    scope,
  })
  return data
}

export async function deleteKbFolder(folderId: number, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/folders/${folderId}`, { params: { scope } })
}

export async function addKbPaper(
  paperId: string,
  paperData: PaperSummary,
  folderId?: number | null,
  scope: KbScope = 'kb',
): Promise<KbPaper> {
  const { data } = await http.post<KbPaper>('/kb/papers', {
    paper_id: paperId,
    paper_data: paperData,
    folder_id: folderId ?? null,
    scope,
  })
  return data
}

export async function removeKbPaper(paperId: string, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/papers/${paperId}`, { params: { scope } })
}

export async function moveKbPapers(
  paperIds: string[],
  targetFolderId: number | null,
  scope: KbScope = 'kb',
): Promise<{ ok: boolean; moved: number }> {
  const { data } = await http.patch<{ ok: boolean; moved: number }>('/kb/papers/move', {
    paper_ids: paperIds,
    target_folder_id: targetFolderId,
    scope,
  })
  return data
}

export async function renameKbPaper(paperId: string, title: string, scope: KbScope = 'kb'): Promise<KbPaper> {
  const { data } = await http.patch<KbPaper>(`/kb/papers/${paperId}/rename`, { title, scope })
  return data
}

// ---------------------------------------------------------------------------
// Notes / Files
// ---------------------------------------------------------------------------

export async function fetchNotes(paperId: string, scope: KbScope = 'kb'): Promise<KbNotesResponse> {
  const { data } = await http.get<KbNotesResponse>(`/kb/papers/${paperId}/notes`, { params: { scope } })
  return data
}

export async function createNote(
  paperId: string,
  title: string = '未命名笔记',
  content: string = '',
  scope: KbScope = 'kb',
): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes`, { title, content, scope })
  return data
}

export async function fetchNoteDetail(noteId: number): Promise<KbNote> {
  const { data } = await http.get<KbNote>(`/kb/notes/${noteId}`)
  return data
}

export async function updateNote(
  noteId: number,
  payload: { title?: string; content?: string },
): Promise<KbNote> {
  const { data } = await http.patch<KbNote>(`/kb/notes/${noteId}`, payload)
  return data
}

export async function deleteNote(noteId: number): Promise<void> {
  await http.delete(`/kb/notes/${noteId}`)
}

export async function uploadNoteFile(paperId: string, file: File, scope: KbScope = 'kb'): Promise<KbNote> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes/upload`, form, {
    params: { scope },
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return data
}

export async function addNoteLink(
  paperId: string,
  title: string,
  url: string,
  scope: KbScope = 'kb',
): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes/link`, { title, url, scope })
  return data
}

// ---------------------------------------------------------------------------
// Dismiss
// ---------------------------------------------------------------------------

export async function dismissPaper(paperId: string): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/kb/dismiss', { paper_id: paperId })
  return data
}

// ---------------------------------------------------------------------------
// Compare (SSE streaming)
// ---------------------------------------------------------------------------

export function fetchCompareStream(
  paperIds: string[],
  scope: KbScope = 'kb',
): Promise<Response> {
  return fetch('/api/kb/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ paper_ids: paperIds, scope }),
  })
}

// ---------------------------------------------------------------------------
// Compare Results
// ---------------------------------------------------------------------------

export async function fetchCompareResultsTree(): Promise<KbCompareResultsTree> {
  const { data } = await http.get<KbCompareResultsTree>('/kb/compare-results/tree')
  return data
}

export async function saveCompareResult(
  title: string,
  markdown: string,
  paperIds: string[],
  folderId?: number | null,
): Promise<KbCompareResult> {
  const { data } = await http.post<KbCompareResult>('/kb/compare-results', {
    title,
    markdown,
    paper_ids: paperIds,
    folder_id: folderId ?? null,
  })
  return data
}

export async function fetchCompareResult(resultId: number): Promise<KbCompareResult> {
  const { data } = await http.get<KbCompareResult>(`/kb/compare-results/${resultId}`)
  return data
}

export async function renameCompareResult(resultId: number, title: string): Promise<KbCompareResult> {
  const { data } = await http.patch<KbCompareResult>(`/kb/compare-results/${resultId}`, { title })
  return data
}

export async function deleteCompareResult(resultId: number): Promise<void> {
  await http.delete(`/kb/compare-results/${resultId}`)
}

// ---------------------------------------------------------------------------
// User Settings
// ---------------------------------------------------------------------------

export async function fetchUserSettings(feature: string): Promise<{ settings: Record<string, any>; defaults: Record<string, any> }> {
  const { data } = await http.get(`/user-settings/${feature}`)
  return data
}

export async function saveUserSettings(feature: string, settings: Record<string, any>): Promise<{ settings: Record<string, any>; defaults: Record<string, any> }> {
  const { data } = await http.post(`/user-settings/${feature}`, settings)
  return data
}

// ---------------------------------------------------------------------------
// User Presets
// ---------------------------------------------------------------------------

export interface UserLlmPreset {
  id: number
  name: string
  base_url: string
  api_key: string
  model: string
  max_tokens?: number | null
  temperature?: number | null
  input_hard_limit?: number | null
  input_safety_margin?: number | null
}

export interface UserPromptPreset {
  id: number
  name: string
  prompt_content: string
}

export async function fetchUserLlmPresets(): Promise<{ presets: UserLlmPreset[] }> {
  const { data } = await http.get('/user-presets/llm')
  return data
}

export async function fetchUserPromptPresets(): Promise<{ presets: UserPromptPreset[] }> {
  const { data } = await http.get('/user-presets/prompt')
  return data
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function authSendSms(payload: SmsSendPayload): Promise<SmsSendResponse> {
  const { data } = await http.post<SmsSendResponse>('/auth/sms/send', payload)
  return data
}

export async function authRegister(payload: AuthRegisterPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/register', payload)
  return data
}

export async function authLogin(payload: AuthPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/login', payload)
  return data
}

export async function authLoginSms(payload: AuthSmsLoginPayload): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/login/sms', payload)
  return data
}

export async function authMe(): Promise<AuthMeResponse> {
  const { data } = await http.get<AuthMeResponse>('/auth/me')
  return data
}

export async function checkUsername(username: string, excludeUserId?: number): Promise<{ available: boolean; message: string }> {
  const params: Record<string, any> = { username }
  if (excludeUserId !== undefined) params.exclude_user_id = excludeUserId
  const { data } = await http.get<{ available: boolean; message: string }>('/auth/check-username', { params })
  return data
}

export async function authLogout(): Promise<AuthLogoutResponse> {
  const { data } = await http.post<AuthLogoutResponse>('/auth/logout')
  return data
}

export async function fetchAuthProfile(): Promise<AuthActionResponse> {
  const { data } = await http.get<AuthActionResponse>('/auth/profile')
  return data
}

export async function updateAuthProfile(payload: {
  nickname?: string
  username?: string
}): Promise<AuthActionResponse> {
  const { data } = await http.put<AuthActionResponse>('/auth/profile', payload)
  return data
}

export async function setAuthPassword(payload: { password: string }): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/profile/set-password', payload)
  return data
}

export async function changeAuthPassword(payload: {
  old_password: string
  new_password: string
}): Promise<AuthActionResponse> {
  const { data } = await http.post<AuthActionResponse>('/auth/profile/change-password', payload)
  return data
}

// ---------------------------------------------------------------------------
// Idea API
// ---------------------------------------------------------------------------

// -- Atoms --

export async function fetchIdeaAtoms(params?: {
  paper_id?: string
  atom_type?: string
  query?: string
  limit?: number
  offset?: number
}): Promise<IdeaAtomsResponse> {
  const { data } = await http.get<IdeaAtomsResponse>('/idea/atoms', { params })
  return data
}

export async function fetchIdeaAtom(atomId: number): Promise<IdeaAtomResponse> {
  const { data } = await http.get<IdeaAtomResponse>(`/idea/atoms/${atomId}`)
  return data
}

export async function deleteIdeaAtom(atomId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/atoms/${atomId}`)
  return data
}

// -- Candidates --

export async function fetchIdeaCandidates(params?: {
  status?: string
  query?: string
  limit?: number
  offset?: number
}): Promise<IdeaCandidatesResponse> {
  const { data } = await http.get<IdeaCandidatesResponse>('/idea/candidates', { params })
  return data
}

export async function fetchIdeaCandidate(candidateId: number): Promise<IdeaCandidateResponse> {
  const { data } = await http.get<IdeaCandidateResponse>(`/idea/candidates/${candidateId}`)
  return data
}

export async function reviewIdeaCandidate(candidateId: number, payload: {
  action: 'approve' | 'reject' | 'revise'
  feedback?: string
  scores?: Record<string, number>
}): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(`/idea/candidates/${candidateId}/review`, payload)
  return data
}

export async function createIdeaFeedback(payload: {
  candidate_id?: number
  atom_id?: number
  action: string
  context?: Record<string, any>
}): Promise<IdeaFeedbackResponse> {
  const { data } = await http.post<IdeaFeedbackResponse>('/idea/feedback', payload)
  return data
}

// -- Plans --

export async function fetchIdeaPlan(candidateId: number): Promise<IdeaPlanResponse> {
  const { data } = await http.get<IdeaPlanResponse>(`/idea/plans/${candidateId}`)
  return data
}

export async function createIdeaPlan(candidateId: number, payload: Partial<IdeaPlan>): Promise<IdeaPlanResponse> {
  const { data } = await http.post<IdeaPlanResponse>(`/idea/plans`, { candidate_id: candidateId, ...payload })
  return data
}

// -- Exemplars --

export async function fetchIdeaExemplars(params?: {
  query?: string
  limit?: number
  offset?: number
}): Promise<IdeaExemplarsResponse> {
  const { data } = await http.get<IdeaExemplarsResponse>('/idea/exemplars', { params })
  return data
}

export async function createIdeaExemplar(payload: {
  candidate_id: number
  name: string
  description?: string
  tags?: string[]
}): Promise<{ ok: boolean; exemplar: IdeaExemplar }> {
  const { data } = await http.post<{ ok: boolean; exemplar: IdeaExemplar }>('/idea/exemplars', payload)
  return data
}

export async function deleteIdeaExemplar(exemplarId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/exemplars/${exemplarId}`)
  return data
}

// -- Benchmarks --

export async function fetchIdeaBenchmarks(params?: {
  query?: string
  limit?: number
  offset?: number
}): Promise<IdeaBenchmarksResponse> {
  const { data } = await http.get<IdeaBenchmarksResponse>('/idea/benchmarks', { params })
  return data
}

export async function createIdeaBenchmark(payload: {
  name: string
  description?: string
  questions?: string[]
  expected_outputs?: string[]
}): Promise<{ ok: boolean; benchmark: IdeaBenchmark }> {
  const { data } = await http.post<{ ok: boolean; benchmark: IdeaBenchmark }>('/idea/benchmarks', payload)
  return data
}

export async function deleteIdeaBenchmark(benchmarkId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/benchmarks/${benchmarkId}`)
  return data
}

// -- Stats --

export async function fetchIdeaStats(): Promise<IdeaStatsResponse> {
  const { data } = await http.get<IdeaStatsResponse>('/idea/stats')
  return data
}

// -- Digest --

export async function fetchIdeaDigest(date: string): Promise<IdeaDigestResponse> {
  const { data } = await http.get<IdeaDigestResponse>(`/idea/digest/${date}`)
  return data
}

// ---------------------------------------------------------------------------
// Admin: System Config
// ---------------------------------------------------------------------------

export interface AdminLlmConfig {
  id: number
  name: string
  remark?: string
  base_url: string
  api_key: string
  model: string
  max_tokens?: number | null
  temperature?: number | null
  concurrency?: number | null
}

export interface AdminPromptConfig {
  id: number
  name: string
  remark?: string
  prompt_content: string
}

export async function adminFetchSystemConfig(): Promise<{ groups: any[] }> {
  const { data } = await http.get('/admin/config')
  return data
}

export async function adminFetchLlmConfigs(): Promise<{ configs: AdminLlmConfig[] }> {
  const { data } = await http.get('/admin/llm-configs')
  return data
}

export async function adminFetchPromptConfigs(): Promise<{ configs: AdminPromptConfig[] }> {
  const { data } = await http.get('/admin/prompt-configs')
  return data
}

export interface BatchApplyItem_Llm {
  config_id: number
  prefix: string
}

export interface BatchApplyItem_Prompt {
  config_id: number
  variable: string
}

export async function adminBatchApplyConfigs(
  llmApplies: BatchApplyItem_Llm[],
  promptApplies: BatchApplyItem_Prompt[],
): Promise<{ ok: boolean; message: string; applied_count: number; errors: string[] }> {
  const { data } = await http.post('/admin/config/batch-apply', {
    llm_applies: llmApplies,
    prompt_applies: promptApplies,
  })
  return data
}
