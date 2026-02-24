import axios from 'axios'
import type {
  DatesResponse,
  PapersResponse,
  PaperDetailResponse,
  DigestResponse,
  PipelineStatusResponse,
  KbTree,
  KbFolder,
  KbPaper,
  KbNote,
  KbNotesResponse,
  KbAnnotation,
  KbAnnotationsResponse,
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
  AdminUsersResponse,
  UserTier,
  UserRole,
  PipelineRunStatus,
  ScheduleConfig,
  SystemConfigResponse,
  SystemConfigUpdateResponse,
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

/** 获取所有可用日期 */
export async function fetchDates(): Promise<DatesResponse> {
  const { data } = await http.get<DatesResponse>('/dates')
  return data
}

/** 获取某天的论文列表 */
export async function fetchPapers(
  date: string,
  search?: string,
  institution?: string,
): Promise<PapersResponse> {
  const { data } = await http.get<PapersResponse>('/papers', {
    params: { date, search: search || undefined, institution: institution || undefined },
  })
  return data
}

/** 获取单篇论文详情 */
export async function fetchPaperDetail(paperId: string): Promise<PaperDetailResponse> {
  const { data } = await http.get<PaperDetailResponse>(`/papers/${paperId}`)
  return data
}

/** 获取每日摘要 */
export async function fetchDigest(date: string): Promise<DigestResponse> {
  const { data } = await http.get<DigestResponse>(`/digest/${date}`)
  return data
}

/** 获取 Pipeline 状态 */
export async function fetchPipelineStatus(date: string): Promise<PipelineStatusResponse> {
  const { data } = await http.get<PipelineStatusResponse>('/pipeline/status', {
    params: { date },
  })
  return data
}

// ---------------------------------------------------------------------------
// Knowledge Base API
// ---------------------------------------------------------------------------

export type KbScope = 'kb' | 'inspiration'

/** 获取知识库完整树 */
export async function fetchKbTree(scope: KbScope = 'kb'): Promise<KbTree> {
  const { data } = await http.get<KbTree>('/kb/tree', { params: { scope } })
  return data
}

/** 创建文件夹 */
export async function createKbFolder(name: string, parentId?: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.post<KbFolder>('/kb/folders', {
    name,
    parent_id: parentId ?? null,
    scope,
  })
  return data
}

/** 重命名文件夹 */
export async function renameKbFolder(folderId: number, name: string, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}`, { name, scope })
  return data
}

/** 移动文件夹到新的父目录 (null = 根目录) */
export async function moveKbFolder(folderId: number, targetParentId: number | null, scope: KbScope = 'kb'): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}/move`, {
    target_parent_id: targetParentId,
    scope,
  })
  return data
}

/** 删除文件夹 */
export async function deleteKbFolder(folderId: number, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/folders/${folderId}`, { params: { scope } })
}

/** 将论文加入知识库 */
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

/** 从知识库移除论文 */
export async function removeKbPaper(paperId: string, scope: KbScope = 'kb'): Promise<void> {
  await http.delete(`/kb/papers/${paperId}`, { params: { scope } })
}

/** 批量移动论文到目标文件夹 (null = 根目录) */
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

// ---------------------------------------------------------------------------
// Note / File API
// ---------------------------------------------------------------------------

/** 获取论文下所有笔记/文件 */
export async function fetchNotes(paperId: string, scope: KbScope = 'kb'): Promise<KbNotesResponse> {
  const { data } = await http.get<KbNotesResponse>(`/kb/papers/${paperId}/notes`, { params: { scope } })
  return data
}

/** 新建 Markdown 笔记 */
export async function createNote(
  paperId: string,
  title: string = '未命名笔记',
  content: string = '',
  scope: KbScope = 'kb',
): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes`, { title, content, scope })
  return data
}

/** 获取单个笔记详情（含内容） — scope 不需要，note_id 全局唯一 */
export async function fetchNoteDetail(noteId: number): Promise<KbNote> {
  const { data } = await http.get<KbNote>(`/kb/notes/${noteId}`)
  return data
}

/** 更新笔记标题/内容 — scope 不需要，note_id 全局唯一 */
export async function updateNote(
  noteId: number,
  payload: { title?: string; content?: string },
): Promise<KbNote> {
  const { data } = await http.patch<KbNote>(`/kb/notes/${noteId}`, payload)
  return data
}

/** 删除笔记/文件 — scope 不需要，note_id 全局唯一 */
export async function deleteNote(noteId: number): Promise<void> {
  await http.delete(`/kb/notes/${noteId}`)
}

/** 上传文件到论文 */
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

/** 添加外部链接 */
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
// Paper Compare (SSE streaming)
// ---------------------------------------------------------------------------

/** Initiate a streaming comparison analysis of 2-5 KB papers.
 *  Returns a raw Response whose body is an SSE text/event-stream.
 *  Each `data:` line is a JSON-encoded string chunk; the final line is `data: [DONE]`.
 */
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
// Dismiss Paper API
// ---------------------------------------------------------------------------

/** 标记论文为不感兴趣 */
export async function dismissPaper(paperId: string): Promise<{ ok: boolean }> {
  const { data } = await http.post<{ ok: boolean }>('/kb/dismiss', { paper_id: paperId })
  return data
}

// ---------------------------------------------------------------------------
// Paper Rename API
// ---------------------------------------------------------------------------

/** 重命名论文显示标题 */
export async function renameKbPaper(
  paperId: string,
  title: string,
  scope: KbScope = 'kb',
): Promise<KbPaper> {
  const { data } = await http.patch<KbPaper>(`/kb/papers/${paperId}/rename`, { title, scope })
  return data
}

// ---------------------------------------------------------------------------
// Compare Results API
// ---------------------------------------------------------------------------

/** 获取对比分析结果树 */
export async function fetchCompareResultsTree(): Promise<KbCompareResultsTree> {
  const { data } = await http.get<KbCompareResultsTree>('/kb/compare-results/tree')
  return data
}

/** 保存对比分析结果 */
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

/** 获取单个对比分析结果 */
export async function fetchCompareResult(resultId: number): Promise<KbCompareResult> {
  const { data } = await http.get<KbCompareResult>(`/kb/compare-results/${resultId}`)
  return data
}

/** 重命名对比分析结果 */
export async function renameCompareResult(resultId: number, title: string): Promise<KbCompareResult> {
  const { data } = await http.patch<KbCompareResult>(`/kb/compare-results/${resultId}`, { title })
  return data
}

/** 移动对比分析结果到文件夹 */
export async function moveCompareResult(resultId: number, targetFolderId: number | null): Promise<KbCompareResult> {
  const { data } = await http.patch<KbCompareResult>(`/kb/compare-results/${resultId}/move`, {
    target_folder_id: targetFolderId,
  })
  return data
}

/** 删除对比分析结果 */
export async function deleteCompareResult(resultId: number): Promise<void> {
  await http.delete(`/kb/compare-results/${resultId}`)
}

// ---------------------------------------------------------------------------
// Annotation API
// ---------------------------------------------------------------------------

/** 获取论文的所有批注 */
export async function fetchAnnotations(paperId: string, scope: KbScope = 'kb'): Promise<KbAnnotationsResponse> {
  const { data } = await http.get<KbAnnotationsResponse>(`/kb/papers/${paperId}/annotations`, { params: { scope } })
  return data
}

/** 创建批注 */
export async function createAnnotation(
  paperId: string,
  payload: {
    page: number
    type?: string
    content?: string
    color?: string
    position_data?: string
  },
  scope: KbScope = 'kb',
): Promise<KbAnnotation> {
  const { data } = await http.post<KbAnnotation>(`/kb/papers/${paperId}/annotations`, { ...payload, scope })
  return data
}

/** 更新批注 — scope 不需要，annotation_id 全局唯一 */
export async function updateAnnotation(
  annotationId: number,
  payload: { content?: string; color?: string },
): Promise<KbAnnotation> {
  const { data } = await http.patch<KbAnnotation>(`/kb/annotations/${annotationId}`, payload)
  return data
}

/** 删除批注 — scope 不需要，annotation_id 全局唯一 */
export async function deleteAnnotation(annotationId: number): Promise<void> {
  await http.delete(`/kb/annotations/${annotationId}`)
}

// ---------------------------------------------------------------------------
// Auth API
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
// Admin API
// ---------------------------------------------------------------------------

export async function fetchAdminUsers(): Promise<AdminUsersResponse> {
  const { data } = await http.get<AdminUsersResponse>('/admin/users')
  return data
}

export async function updateAdminUserTier(
  userId: number,
  tier: UserTier,
): Promise<AuthActionResponse> {
  const { data } = await http.patch<AuthActionResponse>(`/admin/users/${userId}/tier`, { tier })
  return data
}

export async function updateAdminUserRole(
  userId: number,
  role: UserRole,
): Promise<AuthActionResponse> {
  const { data } = await http.patch<AuthActionResponse>(`/admin/users/${userId}/role`, { role })
  return data
}

// ---------------------------------------------------------------------------
// Pipeline API
// ---------------------------------------------------------------------------

export async function runPipeline(params: {
  pipeline?: string
  date?: string
  sllm?: number | null
  zo?: string
  force?: boolean
  // Arxiv 检索参数
  days?: number | null
  categories?: string | null
  extra_query?: string | null
  max_papers?: number | null
  anchor_tz?: string | null
}): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/pipeline/run', params)
  return data
}

export async function getPipelineRunStatus(): Promise<PipelineRunStatus> {
  const { data } = await http.get<PipelineRunStatus>('/admin/pipeline/status')
  return data
}

export async function stopPipeline(): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/pipeline/stop')
  return data
}

export async function getScheduleConfig(): Promise<ScheduleConfig> {
  const { data } = await http.get<ScheduleConfig>('/admin/schedule')
  return data
}

export async function updateScheduleConfig(config: {
  enabled: boolean
  hour: number
  minute: number
  pipeline?: string
  sllm?: number | null
  zo?: string
  user_id?: number | null
}): Promise<{ ok: boolean; schedule: ScheduleConfig }> {
  const { data } = await http.post<{ ok: boolean; schedule: ScheduleConfig }>('/admin/schedule', config)
  return data
}

// ---------------------------------------------------------------------------
// User Settings API
// ---------------------------------------------------------------------------

export interface UserSettingsResponse {
  ok: boolean
  feature: string
  settings: Record<string, any>
  defaults: Record<string, any>
}

/** 获取指定功能的用户设置（含默认值） */
export async function fetchUserSettings(feature: string): Promise<UserSettingsResponse> {
  const { data } = await http.get<UserSettingsResponse>(`/user/settings/${feature}`)
  return data
}

/** 保存指定功能的用户设置 */
export async function saveUserSettings(feature: string, settings: Record<string, any>): Promise<UserSettingsResponse> {
  const { data } = await http.put<UserSettingsResponse>(`/user/settings/${feature}`, { settings })
  return data
}

// ---------------------------------------------------------------------------
// System Config API
// ---------------------------------------------------------------------------

/** 获取系统配置 */
export async function getSystemConfig(): Promise<SystemConfigResponse> {
  const { data } = await http.get<SystemConfigResponse>('/admin/config')
  return data
}

/** 更新系统配置 */
export async function updateSystemConfig(config: Record<string, any>): Promise<SystemConfigUpdateResponse> {
  const { data } = await http.post<SystemConfigUpdateResponse>('/admin/config', { config })
  return data
}

/** 重置系统配置为默认值 */
export async function resetSystemConfig(): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/admin/config/reset')
  return data
}

// ---------------------------------------------------------------------------
// LLM Config API
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

export interface LlmConfigsResponse {
  ok: boolean
  configs: LlmConfig[]
}

export interface LlmConfigResponse {
  ok: boolean
  config: LlmConfig
}

export interface ApplyLlmConfigResponse {
  ok: boolean
  message: string
  config: Record<string, any>
}

/** 获取所有模型配置 */
export async function fetchLlmConfigs(): Promise<LlmConfigsResponse> {
  const { data } = await http.get<LlmConfigsResponse>('/admin/llm-configs')
  return data
}

/** 获取单个模型配置 */
export async function fetchLlmConfig(configId: number): Promise<LlmConfigResponse> {
  const { data } = await http.get<LlmConfigResponse>(`/admin/llm-configs/${configId}`)
  return data
}

/** 创建模型配置 */
export async function createLlmConfig(config: Omit<LlmConfig, 'id' | 'created_at' | 'updated_at'>): Promise<LlmConfigResponse> {
  const { data } = await http.post<LlmConfigResponse>('/admin/llm-configs', config)
  return data
}

/** 更新模型配置 */
export async function updateLlmConfig(configId: number, config: Partial<LlmConfig>): Promise<LlmConfigResponse> {
  const { data } = await http.put<LlmConfigResponse>(`/admin/llm-configs/${configId}`, config)
  return data
}

/** 删除模型配置 */
export async function deleteLlmConfig(configId: number): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string }>(`/admin/llm-configs/${configId}`)
  return data
}

/** 应用模型配置到config.py */
export async function applyLlmConfig(configId: number, usagePrefix: string): Promise<ApplyLlmConfigResponse> {
  const { data } = await http.post<ApplyLlmConfigResponse>(`/admin/llm-configs/${configId}/apply`, {
    usage_prefix: usagePrefix,
  })
  return data
}

// ---------------------------------------------------------------------------
// Prompt Config API
// ---------------------------------------------------------------------------

export interface PromptConfig {
  id: number
  name: string
  remark?: string
  prompt_content: string
  created_at: string
  updated_at: string
}

export interface PromptConfigsResponse {
  ok: boolean
  configs: PromptConfig[]
}

export interface PromptConfigResponse {
  ok: boolean
  config: PromptConfig
}

export interface ApplyPromptConfigResponse {
  ok: boolean
  message: string
  config: Record<string, any>
}

/** 获取所有提示词配置 */
export async function fetchPromptConfigs(): Promise<PromptConfigsResponse> {
  const { data } = await http.get<PromptConfigsResponse>('/admin/prompt-configs')
  return data
}

/** 获取单个提示词配置 */
export async function fetchPromptConfig(configId: number): Promise<PromptConfigResponse> {
  const { data } = await http.get<PromptConfigResponse>(`/admin/prompt-configs/${configId}`)
  return data
}

/** 创建提示词配置 */
export async function createPromptConfig(config: Omit<PromptConfig, 'id' | 'created_at' | 'updated_at'>): Promise<PromptConfigResponse> {
  const { data } = await http.post<PromptConfigResponse>('/admin/prompt-configs', config)
  return data
}

/** 更新提示词配置 */
export async function updatePromptConfig(configId: number, config: Partial<PromptConfig>): Promise<PromptConfigResponse> {
  const { data } = await http.put<PromptConfigResponse>(`/admin/prompt-configs/${configId}`, config)
  return data
}

/** 删除提示词配置 */
export async function deletePromptConfig(configId: number): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.delete<{ ok: boolean; message: string }>(`/admin/prompt-configs/${configId}`)
  return data
}

/** 应用提示词配置到config.py */
export async function applyPromptConfig(configId: number, variableName: string): Promise<ApplyPromptConfigResponse> {
  const { data } = await http.post<ApplyPromptConfigResponse>(`/admin/prompt-configs/${configId}/apply`, {
    variable_name: variableName,
  })
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

export interface BatchApplyConfigResponse {
  ok: boolean
  message: string
  applied_count: number
  errors: string[]
  config: Record<string, any>
}

/** 批量应用模型配置和提示词配置（一次性写入） */
export async function batchApplyConfigs(
  llmApplies: BatchApplyItem_Llm[],
  promptApplies: BatchApplyItem_Prompt[],
): Promise<BatchApplyConfigResponse> {
  const { data } = await http.post<BatchApplyConfigResponse>('/admin/config/batch-apply', {
    llm_applies: llmApplies,
    prompt_applies: promptApplies,
  })
  return data
}

// ---------------------------------------------------------------------------
// User LLM Presets API
// ---------------------------------------------------------------------------

import type { UserLlmPreset, UserPromptPreset } from '../types/paper'

export interface UserLlmPresetsResponse {
  ok: boolean
  presets: UserLlmPreset[]
}

export interface UserLlmPresetResponse {
  ok: boolean
  preset: UserLlmPreset
}

/** 获取用户的所有模型预设 */
export async function fetchUserLlmPresets(): Promise<UserLlmPresetsResponse> {
  const { data } = await http.get<UserLlmPresetsResponse>('/user/llm-presets')
  return data
}

/** 创建模型预设 */
export async function createUserLlmPreset(preset: Omit<UserLlmPreset, 'id' | 'user_id' | 'created_at' | 'updated_at'>): Promise<UserLlmPresetResponse> {
  const { data } = await http.post<UserLlmPresetResponse>('/user/llm-presets', preset)
  return data
}

/** 更新模型预设 */
export async function updateUserLlmPreset(presetId: number, preset: Partial<UserLlmPreset>): Promise<UserLlmPresetResponse> {
  const { data } = await http.put<UserLlmPresetResponse>(`/user/llm-presets/${presetId}`, preset)
  return data
}

/** 删除模型预设 */
export async function deleteUserLlmPreset(presetId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/user/llm-presets/${presetId}`)
  return data
}

// ---------------------------------------------------------------------------
// User Prompt Presets API
// ---------------------------------------------------------------------------

export interface UserPromptPresetsResponse {
  ok: boolean
  presets: UserPromptPreset[]
}

export interface UserPromptPresetResponse {
  ok: boolean
  preset: UserPromptPreset
}

/** 获取用户的所有提示词预设 */
export async function fetchUserPromptPresets(): Promise<UserPromptPresetsResponse> {
  const { data } = await http.get<UserPromptPresetsResponse>('/user/prompt-presets')
  return data
}

/** 创建提示词预设 */
export async function createUserPromptPreset(preset: Omit<UserPromptPreset, 'id' | 'user_id' | 'created_at' | 'updated_at'>): Promise<UserPromptPresetResponse> {
  const { data } = await http.post<UserPromptPresetResponse>('/user/prompt-presets', preset)
  return data
}

/** 更新提示词预设 */
export async function updateUserPromptPreset(presetId: number, preset: Partial<UserPromptPreset>): Promise<UserPromptPresetResponse> {
  const { data } = await http.put<UserPromptPresetResponse>(`/user/prompt-presets/${presetId}`, preset)
  return data
}

/** 删除提示词预设 */
export async function deleteUserPromptPreset(presetId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/user/prompt-presets/${presetId}`)
  return data
}

// ---------------------------------------------------------------------------
// Idea Generation v2 API (灵感生成)
// ---------------------------------------------------------------------------

import type {
  IdeaAtom,
  IdeaCandidate,
  IdeaPlan,
  IdeaFeedback,
  IdeaExemplar,
  IdeaBenchmark,
  IdeaPromptVersion,
} from '../types/paper'

// -- Atoms --

export interface IdeaAtomsResponse { ok: boolean; atoms: IdeaAtom[] }
export interface IdeaAtomResponse { ok: boolean; atom: IdeaAtom }

export async function fetchIdeaAtoms(params?: {
  paper_id?: string; atom_type?: string; query?: string; limit?: number; offset?: number
}): Promise<IdeaAtomsResponse> {
  const { data } = await http.get<IdeaAtomsResponse>('/idea/atoms', { params })
  return data
}

export async function fetchIdeaAtom(atomId: number): Promise<IdeaAtomResponse> {
  const { data } = await http.get<IdeaAtomResponse>(`/idea/atoms/${atomId}`)
  return data
}

export async function updateIdeaAtom(atomId: number, payload: Partial<IdeaAtom>): Promise<IdeaAtomResponse> {
  const { data } = await http.put<IdeaAtomResponse>(`/idea/atoms/${atomId}`, payload)
  return data
}

export async function deleteIdeaAtom(atomId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/atoms/${atomId}`)
  return data
}

// -- Candidates --

export interface IdeaCandidatesResponse { ok: boolean; candidates: IdeaCandidate[] }
export interface IdeaCandidateResponse { ok: boolean; candidate: IdeaCandidate }

export async function fetchIdeaCandidates(params?: {
  status?: string; query?: string; limit?: number; offset?: number
}): Promise<IdeaCandidatesResponse> {
  const { data } = await http.get<IdeaCandidatesResponse>('/idea/candidates', { params })
  return data
}

export async function fetchIdeaCandidate(candidateId: number): Promise<IdeaCandidateResponse> {
  const { data } = await http.get<IdeaCandidateResponse>(`/idea/candidates/${candidateId}`)
  return data
}

export async function updateIdeaCandidate(candidateId: number, payload: Partial<IdeaCandidate>): Promise<IdeaCandidateResponse> {
  const { data } = await http.put<IdeaCandidateResponse>(`/idea/candidates/${candidateId}`, payload)
  return data
}

export async function deleteIdeaCandidate(candidateId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/candidates/${candidateId}`)
  return data
}

export async function generateIdeas(payload: {
  question_id?: number; target_paper_ids?: string[]; strategy?: string; input_atom_ids?: number[]
}): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>('/idea/generate', payload)
  return data
}

export async function reviewIdeaCandidate(candidateId: number, payload: {
  action: 'approve' | 'reject' | 'revise'; feedback?: string; scores?: Record<string, number>
}): Promise<{ ok: boolean; message: string }> {
  const { data } = await http.post<{ ok: boolean; message: string }>(`/idea/candidates/${candidateId}/review`, payload)
  return data
}

// -- Plans --

export interface IdeaPlanResponse { ok: boolean; plan: IdeaPlan }

export async function fetchIdeaPlan(candidateId: number): Promise<IdeaPlanResponse> {
  const { data } = await http.get<IdeaPlanResponse>(`/idea/plans/${candidateId}`)
  return data
}

export async function createIdeaPlan(candidateId: number, payload: Partial<IdeaPlan>): Promise<IdeaPlanResponse> {
  const { data } = await http.post<IdeaPlanResponse>(`/idea/plans`, { candidate_id: candidateId, ...payload })
  return data
}

export function streamGeneratePlan(candidateId: number): EventSource {
  // Returns a fetch-based SSE stream for plan generation
  // Caller should use fetch() directly for SSE with POST
  throw new Error('Use fetchGeneratePlanStream instead')
}

export async function fetchGeneratePlanStream(
  candidateId: number,
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('token') || sessionStorage.getItem('token') || ''
  const response = await fetch('/api/idea/plans/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ candidate_id: candidateId }),
    signal,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`生成失败 (${response.status}): ${text}`)
  }
  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (payload === '[DONE]') return
      try {
        onChunk(JSON.parse(payload) as string)
      } catch {
        onChunk(payload)
      }
    }
  }
}

export async function updateIdeaPlan(planId: number, payload: Partial<IdeaPlan>): Promise<IdeaPlanResponse> {
  const { data } = await http.put<IdeaPlanResponse>(`/idea/plans/${planId}`, payload)
  return data
}

export async function deleteIdeaPlan(planId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/plans/${planId}`)
  return data
}

// -- Feedback --

export interface IdeaFeedbackResponse { ok: boolean; feedback: IdeaFeedback }
export interface IdeaFeedbackListResponse { ok: boolean; feedback_events: IdeaFeedback[] }

export async function createIdeaFeedback(payload: {
  candidate_id?: number; atom_id?: number; action: string; context?: Record<string, any>
}): Promise<IdeaFeedbackResponse> {
  const { data } = await http.post<IdeaFeedbackResponse>('/idea/feedback', payload)
  return data
}


export async function fetchIdeaFeedback(params?: {
  event_type?: string; candidate_id?: number; atom_id?: number; limit?: number; offset?: number
}): Promise<IdeaFeedbackListResponse> {
  const { data } = await http.get<IdeaFeedbackListResponse>('/idea/feedback', { params })
  return data
}

// -- Exemplars --

export interface IdeaExemplarsResponse { ok: boolean; exemplars: IdeaExemplar[] }
export interface IdeaExemplarResponse { ok: boolean; exemplar: IdeaExemplar }

export async function fetchIdeaExemplars(params?: {
  query?: string; limit?: number; offset?: number
}): Promise<IdeaExemplarsResponse> {
  const { data } = await http.get<IdeaExemplarsResponse>('/idea/exemplars', { params })
  return data
}

export async function fetchIdeaExemplar(exemplarId: number): Promise<IdeaExemplarResponse> {
  const { data } = await http.get<IdeaExemplarResponse>(`/idea/exemplars/${exemplarId}`)
  return data
}

export async function createIdeaExemplar(payload: {
  candidate_id: number; name: string; description?: string; tags?: string[]
}): Promise<IdeaExemplarResponse> {
  const { data } = await http.post<IdeaExemplarResponse>('/idea/exemplars', payload)
  return data
}

export async function updateIdeaExemplar(exemplarId: number, payload: Partial<IdeaExemplar>): Promise<IdeaExemplarResponse> {
  const { data } = await http.put<IdeaExemplarResponse>(`/idea/exemplars/${exemplarId}`, payload)
  return data
}

export async function deleteIdeaExemplar(exemplarId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/exemplars/${exemplarId}`)
  return data
}

// -- Benchmarks --

export interface IdeaBenchmarksResponse { ok: boolean; benchmarks: IdeaBenchmark[] }
export interface IdeaBenchmarkResponse { ok: boolean; benchmark: IdeaBenchmark }

export async function fetchIdeaBenchmarks(params?: {
  query?: string; limit?: number; offset?: number
}): Promise<IdeaBenchmarksResponse> {
  const { data } = await http.get<IdeaBenchmarksResponse>('/idea/benchmarks', { params })
  return data
}

export async function fetchIdeaBenchmark(benchmarkId: number): Promise<IdeaBenchmarkResponse> {
  const { data } = await http.get<IdeaBenchmarkResponse>(`/idea/benchmarks/${benchmarkId}`)
  return data
}

export async function createIdeaBenchmark(payload: {
  name: string; description?: string; questions?: string[]; expected_outputs?: string[]
}): Promise<IdeaBenchmarkResponse> {
  const { data } = await http.post<IdeaBenchmarkResponse>('/idea/benchmarks', payload)
  return data
}

export async function updateIdeaBenchmark(benchmarkId: number, payload: Partial<IdeaBenchmark>): Promise<IdeaBenchmarkResponse> {
  const { data } = await http.put<IdeaBenchmarkResponse>(`/idea/benchmarks/${benchmarkId}`, payload)
  return data
}

export async function deleteIdeaBenchmark(benchmarkId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/benchmarks/${benchmarkId}`)
  return data
}

// -- Prompt Templates --

export interface IdeaPromptVersionsResponse { ok: boolean; templates: IdeaPromptVersion[] }
export interface IdeaPromptVersionResponse { ok: boolean; template: IdeaPromptVersion }

export async function fetchIdeaPromptVersions(params?: {
  template_type?: string; name?: string; is_active?: boolean; limit?: number; offset?: number
}): Promise<IdeaPromptVersionsResponse> {
  const { data } = await http.get<IdeaPromptVersionsResponse>('/idea/prompt-templates', { params })
  return data
}

export async function fetchIdeaPromptVersion(templateId: number): Promise<IdeaPromptVersionResponse> {
  const { data } = await http.get<IdeaPromptVersionResponse>(`/idea/prompt-templates/${templateId}`)
  return data
}

export async function createIdeaPromptVersion(payload: {
  name: string; template_type: string; content: string; version?: number; is_active?: boolean
}): Promise<IdeaPromptVersionResponse> {
  const { data } = await http.post<IdeaPromptVersionResponse>('/idea/prompt-templates', payload)
  return data
}

export async function updateIdeaPromptVersion(templateId: number, payload: Partial<IdeaPromptVersion>): Promise<IdeaPromptVersionResponse> {
  const { data } = await http.put<IdeaPromptVersionResponse>(`/idea/prompt-templates/${templateId}`, payload)
  return data
}

export async function deleteIdeaPromptVersion(templateId: number): Promise<{ ok: boolean }> {
  const { data } = await http.delete<{ ok: boolean }>(`/idea/prompt-templates/${templateId}`)
  return data
}

// -- Stats --

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

export async function fetchIdeaStats(): Promise<IdeaStatsResponse> {
  const { data } = await http.get<IdeaStatsResponse>('/idea/stats')
  return data
}

// -- Idea Digest (permission-filtered, date-scoped) --

export interface IdeaDigestResponse {
  ok: boolean
  candidates: import('../types/paper').IdeaCandidate[]
  total_available: number
  quota_limit: number | null
  tier: string
}

/** 获取指定日期的灵感推荐（按用户配额过滤来源论文） */
export async function fetchIdeaDigest(date: string): Promise<IdeaDigestResponse> {
  const { data } = await http.get<IdeaDigestResponse>(`/idea/digest/${date}`)
  return data
}