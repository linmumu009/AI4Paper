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
  PaperSummary,
} from '../types/paper'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

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

/** 获取知识库完整树 */
export async function fetchKbTree(): Promise<KbTree> {
  const { data } = await http.get<KbTree>('/kb/tree')
  return data
}

/** 创建文件夹 */
export async function createKbFolder(name: string, parentId?: number | null): Promise<KbFolder> {
  const { data } = await http.post<KbFolder>('/kb/folders', {
    name,
    parent_id: parentId ?? null,
  })
  return data
}

/** 重命名文件夹 */
export async function renameKbFolder(folderId: number, name: string): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}`, { name })
  return data
}

/** 移动文件夹到新的父目录 (null = 根目录) */
export async function moveKbFolder(folderId: number, targetParentId: number | null): Promise<KbFolder> {
  const { data } = await http.patch<KbFolder>(`/kb/folders/${folderId}/move`, {
    target_parent_id: targetParentId,
  })
  return data
}

/** 删除文件夹 */
export async function deleteKbFolder(folderId: number): Promise<void> {
  await http.delete(`/kb/folders/${folderId}`)
}

/** 将论文加入知识库 */
export async function addKbPaper(
  paperId: string,
  paperData: PaperSummary,
  folderId?: number | null,
): Promise<KbPaper> {
  const { data } = await http.post<KbPaper>('/kb/papers', {
    paper_id: paperId,
    paper_data: paperData,
    folder_id: folderId ?? null,
  })
  return data
}

/** 从知识库移除论文 */
export async function removeKbPaper(paperId: string): Promise<void> {
  await http.delete(`/kb/papers/${paperId}`)
}

/** 批量移动论文到目标文件夹 (null = 根目录) */
export async function moveKbPapers(
  paperIds: string[],
  targetFolderId: number | null,
): Promise<{ ok: boolean; moved: number }> {
  const { data } = await http.patch<{ ok: boolean; moved: number }>('/kb/papers/move', {
    paper_ids: paperIds,
    target_folder_id: targetFolderId,
  })
  return data
}

// ---------------------------------------------------------------------------
// Note / File API
// ---------------------------------------------------------------------------

/** 获取论文下所有笔记/文件 */
export async function fetchNotes(paperId: string): Promise<KbNotesResponse> {
  const { data } = await http.get<KbNotesResponse>(`/kb/papers/${paperId}/notes`)
  return data
}

/** 新建 Markdown 笔记 */
export async function createNote(
  paperId: string,
  title: string = '未命名笔记',
  content: string = '',
): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes`, { title, content })
  return data
}

/** 获取单个笔记详情（含内容） */
export async function fetchNoteDetail(noteId: number): Promise<KbNote> {
  const { data } = await http.get<KbNote>(`/kb/notes/${noteId}`)
  return data
}

/** 更新笔记标题/内容 */
export async function updateNote(
  noteId: number,
  payload: { title?: string; content?: string },
): Promise<KbNote> {
  const { data } = await http.patch<KbNote>(`/kb/notes/${noteId}`, payload)
  return data
}

/** 删除笔记/文件 */
export async function deleteNote(noteId: number): Promise<void> {
  await http.delete(`/kb/notes/${noteId}`)
}

/** 上传文件到论文 */
export async function uploadNoteFile(paperId: string, file: File): Promise<KbNote> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes/upload`, form, {
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
): Promise<KbNote> {
  const { data } = await http.post<KbNote>(`/kb/papers/${paperId}/notes/link`, { title, url })
  return data
}
