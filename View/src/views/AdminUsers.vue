<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  fetchAdminUsers,
  updateAdminUserTier,
  updateAdminUserRole,
  runPipeline,
  getPipelineRunStatus,
  stopPipeline,
  getScheduleConfig,
  updateScheduleConfig,
  getSystemConfig,
  updateSystemConfig,
  fetchLlmConfigs,
  createLlmConfig,
  updateLlmConfig,
  deleteLlmConfig,
  applyLlmConfig,
  fetchPromptConfigs,
  createPromptConfig,
  updatePromptConfig,
  deletePromptConfig,
  applyPromptConfig,
} from '../api'
import type {
  AuthUser,
  UserTier,
  UserRole,
  PipelineRunStatus,
  ScheduleConfig,
  SystemConfigGroup,
  LlmConfig,
  PromptConfig,
} from '../types/paper'
import { isSuperAdmin, currentUser } from '../stores/auth'

// ---------------------------------------------------------------------------
// Sidebar menu state
// ---------------------------------------------------------------------------
const activeTab = ref<'users' | 'roles' | 'pipeline' | 'schedule' | 'config' | 'llm-config' | 'prompt-config'>('users')

const menuItems = computed(() => {
  const items: { key: 'users' | 'roles' | 'pipeline' | 'schedule' | 'config' | 'llm-config' | 'prompt-config'; icon: string; label: string; desc: string; group?: string }[] = [
    { key: 'users', icon: '👥', label: '用户等级', desc: '管理用户访问等级', group: '用户' },
  ]
  if (isSuperAdmin.value) {
    items.push({ key: 'roles', icon: '🛡️', label: '权限管理', desc: '管理用户角色权限', group: '用户' })
  }
  items.push(
    { key: 'pipeline', icon: '🚀', label: '脚本执行', desc: '手动运行 Pipeline', group: '运维' },
    { key: 'schedule', icon: '🕐', label: '定时调度', desc: '自动定时执行配置', group: '运维' },
    { key: 'config', icon: '⚙️', label: '系统配置', desc: '管理系统配置项', group: '系统' },
    { key: 'llm-config', icon: '🤖', label: '模型配置', desc: '管理大模型配置', group: '系统' },
    { key: 'prompt-config', icon: '📝', label: '提示词配置', desc: '管理提示词配置', group: '系统' },
  )
  return items
})

// Compute groups for sidebar rendering
const menuGroups = computed(() => {
  const groups: { name: string; items: typeof menuItems.value }[] = []
  const seen = new Set<string>()
  for (const item of menuItems.value) {
    const g = item.group || ''
    if (!seen.has(g)) {
      seen.add(g)
      groups.push({ name: g, items: [] })
    }
    groups.find((x) => x.name === g)!.items.push(item)
  }
  return groups
})

// ---------------------------------------------------------------------------
// User Management
// ---------------------------------------------------------------------------
const users = ref<AuthUser[]>([])
const loading = ref(false)
const error = ref('')
const savingUserId = ref<number | null>(null)

const tierOptions: { label: string; value: UserTier }[] = [
  { label: '普通', value: 'free' },
  { label: 'Pro', value: 'pro' },
  { label: 'Pro+', value: 'pro_plus' },
]

const roleOptions: { label: string; value: UserRole }[] = [
  { label: '普通用户', value: 'user' },
  { label: '管理员', value: 'admin' },
  { label: '超级管理员', value: 'superadmin' },
]

function tierLabel(tier: UserTier) {
  if (tier === 'pro') return 'Pro'
  if (tier === 'pro_plus') return 'Pro+'
  return '普通'
}

function roleLabel(role: UserRole) {
  if (role === 'superadmin') return '超级管理员'
  if (role === 'admin') return '管理员'
  return '普通用户'
}

function roleBadgeClass(role: UserRole) {
  if (role === 'superadmin') return 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
  if (role === 'admin') return 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
  return 'bg-bg-elevated text-text-secondary'
}

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchAdminUsers()
    users.value = res.users
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载用户列表失败'
  } finally {
    loading.value = false
  }
}

async function onTierChange(user: AuthUser, event: Event) {
  const tier = (event.target as HTMLSelectElement).value as UserTier
  if (tier === user.tier) return
  savingUserId.value = user.id
  try {
    const res = await updateAdminUserTier(user.id, tier)
    const idx = users.value.findIndex((u) => u.id === user.id)
    if (idx >= 0) users.value[idx] = res.user
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '更新失败')
  } finally {
    savingUserId.value = null
  }
}

async function onRoleChange(user: AuthUser, event: Event) {
  const role = (event.target as HTMLSelectElement).value as UserRole
  if (role === user.role) return
  if (!confirm(`确定将用户「${user.username}」的角色修改为「${roleLabel(role)}」吗？`)) {
    ;(event.target as HTMLSelectElement).value = user.role
    return
  }
  savingUserId.value = user.id
  try {
    const res = await updateAdminUserRole(user.id, role)
    const idx = users.value.findIndex((u) => u.id === user.id)
    if (idx >= 0) users.value[idx] = res.user
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '更新失败')
    ;(event.target as HTMLSelectElement).value = user.role
  } finally {
    savingUserId.value = null
  }
}

// ---------------------------------------------------------------------------
// Pipeline Execution
// ---------------------------------------------------------------------------
const pipelineStatus = ref<PipelineRunStatus | null>(null)
const pipelineLoading = ref(false)
const pipelineError = ref('')
const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)

// Run form
const runDate = ref(new Date().toISOString().slice(0, 10))
const runPipelineName = ref('default')
const runSllm = ref<number | null>(null)
const runZo = ref('F')
// Arxiv 检索参数
const runDays = ref<number | null>(null)
const runCategories = ref('')
const runQuery = ref('')
const runMaxPapers = ref<number | null>(null)
const showAdvancedParams = ref(false)
const isRunning = computed(() => pipelineStatus.value?.running === true)

// Schedule
const schedule = ref<ScheduleConfig>({
  enabled: false,
  hour: 6,
  minute: 0,
  pipeline: 'daily',
  sllm: null,
  zo: 'F',
})
const scheduleLoading = ref(false)
const scheduleSaving = ref(false)

const logsContainer = ref<HTMLElement | null>(null)

async function loadPipelineStatus() {
  try {
    pipelineStatus.value = await getPipelineRunStatus()
  } catch (e: any) {
    // silently ignore polling errors
  }
}

async function loadSchedule() {
  scheduleLoading.value = true
  try {
    const cfg = await getScheduleConfig()
    schedule.value = cfg
  } catch (e: any) {
    // use defaults
  } finally {
    scheduleLoading.value = false
  }
}

async function handleRunPipeline() {
  pipelineError.value = ''
  pipelineLoading.value = true
  try {
    await runPipeline({
      pipeline: runPipelineName.value,
      date: runDate.value,
      sllm: runSllm.value,
      zo: runZo.value,
      days: runDays.value || null,
      categories: runCategories.value.trim() || null,
      extra_query: runQuery.value.trim() || null,
      max_papers: runMaxPapers.value || null,
    })
    startPolling()
    await loadPipelineStatus()
  } catch (e: any) {
    pipelineError.value = e?.response?.data?.detail || '启动失败'
  } finally {
    pipelineLoading.value = false
  }
}

async function handleStopPipeline() {
  if (!confirm('确定要终止正在运行的 Pipeline 吗？')) return
  try {
    await stopPipeline()
    await loadPipelineStatus()
  } catch (e: any) {
    pipelineError.value = e?.response?.data?.detail || '终止失败'
  }
}

async function handleSaveSchedule() {
  scheduleSaving.value = true
  try {
    const res = await updateScheduleConfig({
      enabled: schedule.value.enabled,
      hour: schedule.value.hour,
      minute: schedule.value.minute,
      pipeline: schedule.value.pipeline,
      sllm: schedule.value.sllm,
      zo: schedule.value.zo,
    })
    schedule.value = res.schedule
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '保存失败')
  } finally {
    scheduleSaving.value = false
  }
}

function startPolling() {
  if (pollTimer.value) return
  pollTimer.value = setInterval(async () => {
    await loadPipelineStatus()
    if (logsContainer.value) {
      logsContainer.value.scrollTop = logsContainer.value.scrollHeight
    }
    if (!pipelineStatus.value?.running) {
      stopPolling()
    }
  }, 2000)
}

function stopPolling() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

const formattedStartedAt = computed(() => {
  if (!pipelineStatus.value?.started_at) return '-'
  try {
    return new Date(pipelineStatus.value.started_at).toLocaleString('zh-CN')
  } catch {
    return pipelineStatus.value.started_at
  }
})

const formattedFinishedAt = computed(() => {
  if (!pipelineStatus.value?.finished_at) return '-'
  try {
    return new Date(pipelineStatus.value.finished_at).toLocaleString('zh-CN')
  } catch {
    return pipelineStatus.value.finished_at
  }
})

const statusLabel = computed(() => {
  if (!pipelineStatus.value) return '未知'
  if (pipelineStatus.value.running) return '运行中'
  if (pipelineStatus.value.exit_code === 0) return '已完成'
  if (pipelineStatus.value.exit_code !== null) return '异常退出'
  return '空闲'
})

const statusColor = computed(() => {
  if (!pipelineStatus.value) return 'text-text-muted'
  if (pipelineStatus.value.running) return 'text-blue-400'
  if (pipelineStatus.value.exit_code === 0) return 'text-green-400'
  if (pipelineStatus.value.exit_code !== null) return 'text-red-400'
  return 'text-text-muted'
})

// ---------------------------------------------------------------------------
// System Config Management
// ---------------------------------------------------------------------------
const configGroups = ref<SystemConfigGroup[]>([])
const configLoading = ref(false)
const configError = ref('')
const configValues = ref<Record<string, any>>({})

async function loadSystemConfig() {
  configLoading.value = true
  configError.value = ''
  try {
    const res = await getSystemConfig()
    configGroups.value = res.groups
    // 初始化配置值
    const values: Record<string, any> = {}
    for (const group of res.groups) {
      for (const item of group.items) {
        values[item.key] = item.value
      }
    }
    configValues.value = values
  } catch (e: any) {
    configError.value = e?.response?.data?.detail || '加载配置失败'
  } finally {
    configLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// System Config: Preset-based UI state & helpers
// ---------------------------------------------------------------------------

// Module-based config structure: each module groups its LLM + prompts together
const configModules = [
  {
    key: 'theme_select',
    label: '主题相关性评分',
    icon: '🎯',
    desc: '对论文进行主题相关性评分，筛选相关论文',
    llmPrefix: 'theme_select' as string | null,
    prompts: [
      { variable: 'theme_select_system_prompt', label: '评分提示词' },
    ],
  },
  {
    key: 'org',
    label: '机构判别',
    icon: '🏛️',
    desc: '提取论文作者机构信息',
    llmPrefix: 'org' as string | null,
    prompts: [
      { variable: 'pdf_info_system_prompt', label: '机构判别提示词' },
    ],
  },
  {
    key: 'summary',
    label: '摘要生成',
    icon: '📄',
    desc: '生成论文中文摘要笔记',
    llmPrefix: 'summary' as string | null,
    prompts: [
      { variable: 'system_prompt', label: '摘要生成提示词' },
    ],
  },
  {
    key: 'summary_limit',
    label: '摘要精简',
    icon: '✂️',
    desc: '压缩摘要各部分至字数上限（按需触发）',
    llmPrefix: 'summary_limit' as string | null,
    prompts: [
      { variable: 'summary_limit_prompt_intro', label: '文章简介精简提示词' },
      { variable: 'summary_limit_prompt_method', label: '重点思路精简提示词' },
      { variable: 'summary_limit_prompt_findings', label: '分析总结精简提示词' },
      { variable: 'summary_limit_prompt_opinion', label: '个人观点精简提示词' },
      { variable: 'summary_limit_prompt_structure_check', label: '结构校验提示词' },
      { variable: 'summary_limit_prompt_structure_rewrite', label: '结构重排提示词' },
      { variable: 'summary_limit_prompt_headline', label: '首行压缩提示词' },
    ],
  },
  {
    key: 'summary_batch',
    label: '批量摘要',
    icon: '📦',
    desc: '批量处理论文摘要生成任务',
    llmPrefix: 'summary_batch' as string | null,
    prompts: [
      { variable: 'summary_batch_system_prompt', label: '批量摘要提示词' },
    ],
  },
  {
    key: 'paper_assets',
    label: '论文结构化抽取',
    icon: '🔬',
    desc: '提取论文结构化数据',
    llmPrefix: null,
    prompts: [
      { variable: 'paper_assets_system_prompt', label: '结构化抽取提示词' },
    ],
  },
]

// Per-prefix selected LLM config IDs
const selectedLlmConfigIds = ref<Record<string, number | null>>({
  theme_select: null,
  org: null,
  summary: null,
  summary_limit: null,
  summary_batch: null,
})

// Per-variable selected prompt config IDs
const selectedPromptConfigIds = ref<Record<string, number | null>>({
  theme_select_system_prompt: null,
  system_prompt: null,
  summary_limit_prompt_intro: null,
  summary_limit_prompt_method: null,
  summary_limit_prompt_findings: null,
  summary_limit_prompt_opinion: null,
  summary_limit_prompt_structure_check: null,
  summary_limit_prompt_structure_rewrite: null,
  summary_limit_prompt_headline: null,
  summary_batch_system_prompt: null,
  pdf_info_system_prompt: null,
  paper_assets_system_prompt: null,
})

// Word limit values (editable)
const wordLimitValues = ref<Record<string, number>>({
  summary_limit_section_limit_intro: 170,
  summary_limit_section_limit_method: 270,
  summary_limit_section_limit_findings: 270,
  summary_limit_section_limit_opinion: 150,
  summary_limit_headline_limit: 18,
})

const wordLimitDefaults: Record<string, number> = {
  summary_limit_section_limit_intro: 170,
  summary_limit_section_limit_method: 270,
  summary_limit_section_limit_findings: 270,
  summary_limit_section_limit_opinion: 150,
  summary_limit_headline_limit: 18,
}

const wordLimitLabels: Record<string, string> = {
  summary_limit_section_limit_intro: '文章简介',
  summary_limit_section_limit_method: '重点思路',
  summary_limit_section_limit_findings: '分析总结',
  summary_limit_section_limit_opinion: '个人观点',
  summary_limit_headline_limit: '首行字数',
}

// Mapping: prefix → config.py model/base_url key names
const prefixModelKey: Record<string, string> = {
  theme_select: 'theme_select_model',
  org: 'org_model',
  summary: 'summary_model',
  summary_limit: 'summary_limit_model',
  summary_batch: 'summary_batch_model',
}
const prefixBaseUrlKey: Record<string, string> = {
  theme_select: 'theme_select_base_url',
  org: 'org_base_url',
  summary: 'summary_base_url',
  summary_limit: 'summary_limit_base_url',
  summary_batch: 'summary_batch_base_url',
}

const applyingModelPrefix = ref<string | null>(null)
const applyingPromptVariable = ref<string | null>(null)
const savingWordLimits = ref(false)
const sysConfigSuccessMsg = ref('')

function detectLlmSelections() {
  for (const mod of configModules) {
    if (!mod.llmPrefix) continue
    const currentModel = configValues.value[prefixModelKey[mod.llmPrefix]]
    const currentUrl = configValues.value[prefixBaseUrlKey[mod.llmPrefix]]
    if (!currentModel && !currentUrl) {
      selectedLlmConfigIds.value[mod.llmPrefix] = null
      continue
    }
    const match = llmConfigs.value.find(c => c.model === currentModel && c.base_url === currentUrl)
    selectedLlmConfigIds.value[mod.llmPrefix] = match?.id ?? null
  }
}

function detectPromptSelections() {
  for (const mod of configModules) {
    for (const prompt of mod.prompts) {
      const currentPrompt = configValues.value[prompt.variable]
      if (!currentPrompt) {
        selectedPromptConfigIds.value[prompt.variable] = null
        continue
      }
      const match = promptConfigs.value.find(c => c.prompt_content === currentPrompt)
      selectedPromptConfigIds.value[prompt.variable] = match?.id ?? null
    }
  }
}

function initWordLimits() {
  for (const key of Object.keys(wordLimitDefaults)) {
    if (key in configValues.value && configValues.value[key] !== undefined) {
      wordLimitValues.value[key] = Number(configValues.value[key]) || wordLimitDefaults[key]
    }
  }
}

// MinerU Token
const mineruTokenValue = ref('')
const mineruTokenVisible = ref(false)
const savingMineruToken = ref(false)

function initMineruToken() {
  mineruTokenValue.value = String(configValues.value['minerU_Token'] || '')
}

async function handleSaveMineruToken() {
  savingMineruToken.value = true
  try {
    await updateSystemConfig({ minerU_Token: mineruTokenValue.value })
    await loadSystemConfig()
    initMineruToken()
    sysConfigSuccessMsg.value = 'MinerU Token 已保存'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '保存失败')
  } finally {
    savingMineruToken.value = false
  }
}

async function handleApplyLlmConfig(prefix: string) {
  const configId = selectedLlmConfigIds.value[prefix]
  if (!configId) return
  applyingModelPrefix.value = prefix
  try {
    await applyLlmConfig(configId, prefix)
    await loadSystemConfig()
    detectLlmSelections()
    sysConfigSuccessMsg.value = '模型配置已应用'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '应用失败')
  } finally {
    applyingModelPrefix.value = null
  }
}

async function handleApplyPromptConfig(variable: string) {
  const configId = selectedPromptConfigIds.value[variable]
  if (!configId) return
  applyingPromptVariable.value = variable
  try {
    await applyPromptConfig(configId, variable)
    await loadSystemConfig()
    detectPromptSelections()
    sysConfigSuccessMsg.value = '提示词配置已应用'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '应用失败')
  } finally {
    applyingPromptVariable.value = null
  }
}

async function handleSaveWordLimits() {
  savingWordLimits.value = true
  try {
    await updateSystemConfig({ ...wordLimitValues.value })
    await loadSystemConfig()
    initWordLimits()
    sysConfigSuccessMsg.value = '字数上限已保存'
    setTimeout(() => { sysConfigSuccessMsg.value = '' }, 2500)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '保存失败')
  } finally {
    savingWordLimits.value = false
  }
}

// Watch activeTab to load config when switching to config tab
watch(activeTab, async (newTab) => {
  if (newTab === 'config') {
    const promises: Promise<void>[] = []
    if (configGroups.value.length === 0) promises.push(loadSystemConfig())
    if (llmConfigs.value.length === 0) promises.push(loadLlmConfigs())
    if (promptConfigs.value.length === 0) promises.push(loadPromptConfigs())
    if (promises.length > 0) await Promise.all(promises)
    detectLlmSelections()
    detectPromptSelections()
    initWordLimits()
    initMineruToken()
  } else if (newTab === 'llm-config' && llmConfigs.value.length === 0) {
    loadLlmConfigs()
  } else if (newTab === 'prompt-config' && promptConfigs.value.length === 0) {
    loadPromptConfigs()
  }
})

// ---------------------------------------------------------------------------
// LLM Config Management
// ---------------------------------------------------------------------------
const llmConfigs = ref<LlmConfig[]>([])
const llmConfigLoading = ref(false)
const llmConfigError = ref('')
const llmConfigEditing = ref<LlmConfig | null>(null)
const llmConfigForm = ref<Partial<LlmConfig>>({})
const llmConfigSaving = ref(false)
const llmConfigApplying = ref<number | null>(null)

const usagePrefixOptions = [
  { value: 'theme_select', label: '主题评分 (theme_select)' },
  { value: 'org', label: '机构判别 (org)' },
  { value: 'summary', label: '摘要生成 (summary)' },
  { value: 'summary_limit', label: '摘要精简 (summary_limit)' },
  { value: 'summary_batch', label: '批量摘要 (summary_batch)' },
]

async function loadLlmConfigs() {
  llmConfigLoading.value = true
  llmConfigError.value = ''
  try {
    const res = await fetchLlmConfigs()
    llmConfigs.value = res.configs
  } catch (e: any) {
    llmConfigError.value = e?.response?.data?.detail || '加载模型配置列表失败'
  } finally {
    llmConfigLoading.value = false
  }
}

function startEditLlmConfig(config?: LlmConfig) {
  if (config) {
    llmConfigEditing.value = config
    llmConfigForm.value = { ...config }
  } else {
    llmConfigEditing.value = null
    llmConfigForm.value = {
      name: '',
      remark: '',
      base_url: '',
      api_key: '',
      model: '',
      max_tokens: undefined,
      temperature: undefined,
      concurrency: undefined,
      input_hard_limit: undefined,
      input_safety_margin: undefined,
      endpoint: undefined,
      completion_window: undefined,
      out_root: undefined,
      jsonl_root: undefined,
    }
  }
}

async function saveLlmConfig() {
  if (!llmConfigForm.value.name || !llmConfigForm.value.base_url || !llmConfigForm.value.api_key || !llmConfigForm.value.model) {
    window.alert('请填写必填字段：名称、base_url、api_key、model')
    return
  }
  llmConfigSaving.value = true
  llmConfigError.value = ''
  try {
    if (llmConfigEditing.value?.id) {
      await updateLlmConfig(llmConfigEditing.value.id, llmConfigForm.value)
    } else {
      await createLlmConfig(llmConfigForm.value as Omit<LlmConfig, 'id' | 'created_at' | 'updated_at'>)
    }
    await loadLlmConfigs()
    llmConfigEditing.value = null
    llmConfigForm.value = {}
  } catch (e: any) {
    llmConfigError.value = e?.response?.data?.detail || '保存配置失败'
    window.alert(llmConfigError.value)
  } finally {
    llmConfigSaving.value = false
  }
}

async function deleteLlmConfigHandler(id: number) {
  if (!window.confirm('确定要删除此配置吗？')) return
  try {
    await deleteLlmConfig(id)
    await loadLlmConfigs()
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '删除配置失败')
  }
}

async function applyLlmConfigHandler(id: number, usagePrefix: string) {
  llmConfigApplying.value = id
  try {
    await applyLlmConfig(id, usagePrefix)
    window.alert(`配置已成功应用到 ${usagePrefix} 前缀`)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '应用配置失败')
  } finally {
    llmConfigApplying.value = null
  }
}

// ---------------------------------------------------------------------------
// Prompt Config Management
// ---------------------------------------------------------------------------
const promptConfigs = ref<PromptConfig[]>([])
const promptConfigLoading = ref(false)
const promptConfigError = ref('')
const promptConfigEditing = ref<PromptConfig | null>(null)
const promptConfigForm = ref<Partial<PromptConfig>>({})
const promptConfigSaving = ref(false)
const promptConfigApplying = ref<number | null>(null)

const promptVariableOptions = [
  { value: 'theme_select_system_prompt', label: '主题评分提示词 (theme_select_system_prompt)' },
  { value: 'system_prompt', label: '摘要生成提示词 (system_prompt)' },
  { value: 'summary_limit_prompt_intro', label: '摘要精简-文章简介 (summary_limit_prompt_intro)' },
  { value: 'summary_limit_prompt_method', label: '摘要精简-重点思路 (summary_limit_prompt_method)' },
  { value: 'summary_limit_prompt_findings', label: '摘要精简-分析总结 (summary_limit_prompt_findings)' },
  { value: 'summary_limit_prompt_opinion', label: '摘要精简-个人观点 (summary_limit_prompt_opinion)' },
  { value: 'summary_limit_prompt_structure_check', label: '摘要结构校验 (summary_limit_prompt_structure_check)' },
  { value: 'summary_limit_prompt_structure_rewrite', label: '摘要结构重排 (summary_limit_prompt_structure_rewrite)' },
  { value: 'summary_limit_prompt_headline', label: '摘要首行压缩 (summary_limit_prompt_headline)' },
  { value: 'summary_batch_system_prompt', label: '批量摘要提示词 (summary_batch_system_prompt)' },
  { value: 'pdf_info_system_prompt', label: '机构判别提示词 (pdf_info_system_prompt)' },
  { value: 'paper_assets_system_prompt', label: '论文结构化抽取 (paper_assets_system_prompt)' },
]

async function loadPromptConfigs() {
  promptConfigLoading.value = true
  promptConfigError.value = ''
  try {
    const res = await fetchPromptConfigs()
    promptConfigs.value = res.configs
  } catch (e: any) {
    promptConfigError.value = e?.response?.data?.detail || '加载提示词配置列表失败'
  } finally {
    promptConfigLoading.value = false
  }
}

function startEditPromptConfig(config?: PromptConfig) {
  if (config) {
    promptConfigEditing.value = config
    promptConfigForm.value = { ...config }
  } else {
    promptConfigEditing.value = null
    promptConfigForm.value = {
      name: '',
      remark: '',
      prompt_content: '',
    }
  }
}

async function savePromptConfig() {
  if (!promptConfigForm.value.name || !promptConfigForm.value.prompt_content) {
    window.alert('请填写必填字段：名称、prompt_content')
    return
  }
  promptConfigSaving.value = true
  promptConfigError.value = ''
  try {
    if (promptConfigEditing.value?.id) {
      await updatePromptConfig(promptConfigEditing.value.id, promptConfigForm.value)
    } else {
      await createPromptConfig(promptConfigForm.value as Omit<PromptConfig, 'id' | 'created_at' | 'updated_at'>)
    }
    await loadPromptConfigs()
    promptConfigEditing.value = null
    promptConfigForm.value = {}
  } catch (e: any) {
    promptConfigError.value = e?.response?.data?.detail || '保存配置失败'
    window.alert(promptConfigError.value)
  } finally {
    promptConfigSaving.value = false
  }
}

async function deletePromptConfigHandler(id: number) {
  if (!window.confirm('确定要删除此配置吗？')) return
  try {
    await deletePromptConfig(id)
    await loadPromptConfigs()
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '删除配置失败')
  }
}

async function applyPromptConfigHandler(id: number, variableName: string) {
  promptConfigApplying.value = id
  try {
    await applyPromptConfig(id, variableName)
    window.alert(`配置已成功应用到变量 ${variableName}`)
  } catch (e: any) {
    window.alert(e?.response?.data?.detail || '应用配置失败')
  } finally {
    promptConfigApplying.value = null
  }
}

onMounted(async () => {
  loadUsers()
  await loadPipelineStatus()
  await loadSchedule()
  if (pipelineStatus.value?.running) {
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="h-full flex overflow-hidden">
    <!-- ============================== -->
    <!-- Sidebar -->
    <!-- ============================== -->
    <aside class="w-56 h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0">
      <!-- Sidebar header -->
      <div class="px-4 pt-5 pb-3 border-b border-border">
        <h2 class="text-base font-bold text-text-primary tracking-tight">⚙ 后台管理</h2>
        <p class="text-[11px] text-text-muted mt-0.5">系统管理与运维</p>
      </div>

      <!-- Menu items (grouped) -->
      <nav class="flex-1 overflow-y-auto p-2">
        <div v-for="group in menuGroups" :key="group.name" class="mb-2">
          <div v-if="group.name" class="px-3 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted/60">
            {{ group.name }}
          </div>
          <div class="space-y-0.5">
            <button
              v-for="item in group.items"
              :key="item.key"
              class="w-full flex items-start gap-3 px-3 py-2.5 rounded-lg text-left bg-transparent border-none cursor-pointer transition-all duration-150"
              :class="activeTab === item.key
                ? 'bg-bg-elevated shadow-sm'
                : 'hover:bg-bg-hover'"
              @click="activeTab = item.key"
            >
              <span class="text-lg leading-none mt-0.5 shrink-0">{{ item.icon }}</span>
              <div class="min-w-0">
                <div
                  class="text-sm font-medium truncate"
                  :class="activeTab === item.key ? 'text-text-primary' : 'text-text-secondary'"
                >{{ item.label }}</div>
                <div class="text-[11px] text-text-muted truncate mt-0.5">{{ item.desc }}</div>
              </div>
              <!-- Active indicator -->
              <div
                v-if="activeTab === item.key"
                class="ml-auto mt-1.5 w-1.5 h-1.5 rounded-full bg-blue-500 shrink-0"
              ></div>
            </button>
          </div>
        </div>
      </nav>

      <!-- Sidebar footer: pipeline status badge -->
      <div class="px-3 py-3 border-t border-border">
        <div class="flex items-center gap-2 text-xs text-text-muted">
          <span
            class="w-2 h-2 rounded-full shrink-0"
            :class="isRunning ? 'bg-blue-400 animate-pulse' : 'bg-gray-500'"
          ></span>
          <span class="truncate">Pipeline: {{ isRunning ? '运行中' : '空闲' }}</span>
        </div>
        <div v-if="schedule.enabled" class="text-[10px] text-text-muted mt-1 pl-4">
          定时 {{ String(schedule.hour).padStart(2, '0') }}:{{ String(schedule.minute).padStart(2, '0') }} 自动执行
        </div>
      </div>
    </aside>

    <!-- ============================== -->
    <!-- Main content area -->
    <!-- ============================== -->
    <div class="flex-1 flex flex-col overflow-hidden">

      <!-- ============================================================= -->
      <!-- Page: User Tier Management -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'users'" class="flex-1 flex flex-col p-6 overflow-hidden">
        <div class="flex items-center justify-between mb-4 shrink-0">
          <div>
            <h1 class="text-lg font-bold text-text-primary">👥 用户等级</h1>
            <p class="text-xs text-text-muted mt-0.5">管理用户的访问等级（Free / Pro / Pro+）</p>
          </div>
          <button
            class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="loadUsers"
          >
            🔄 刷新
          </button>
        </div>

        <div v-if="loading" class="flex-1 flex items-center justify-center text-text-muted">
          <div class="flex items-center gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>
        </div>
        <div v-else-if="error" class="flex-1 flex items-center justify-center text-red-400">{{ error }}</div>

        <div v-else class="flex-1 overflow-auto rounded-xl bg-bg-card border border-border">
          <table class="w-full text-sm">
            <thead class="sticky top-0 z-10">
              <tr class="bg-bg-sidebar border-b border-border">
                <th class="text-left px-4 py-3 font-medium text-text-muted">ID</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">用户名</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">角色</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">当前等级</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">调整等级</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">最后登录</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="u in users"
                :key="u.id"
                class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors"
              >
                <td class="px-4 py-3 text-text-muted font-mono text-xs">{{ u.id }}</td>
                <td class="px-4 py-3 text-text-primary font-medium">
                  {{ u.username }}
                  <span
                    v-if="currentUser?.id === u.id"
                    class="ml-1 text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded-full"
                  >我</span>
                </td>
                <td class="px-4 py-3">
                  <span
                    class="px-2 py-0.5 rounded-full text-xs"
                    :class="roleBadgeClass(u.role)"
                  >
                    {{ roleLabel(u.role) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-text-secondary">{{ tierLabel(u.tier) }}</td>
                <td class="px-4 py-3">
                  <select
                    :value="u.tier"
                    :disabled="savingUserId === u.id"
                    class="px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 cursor-pointer disabled:opacity-60 transition-all"
                    @change="onTierChange(u, $event)"
                  >
                    <option v-for="opt in tierOptions" :key="opt.value" :value="opt.value">
                      {{ opt.label }}
                    </option>
                  </select>
                </td>
                <td class="px-4 py-3 text-text-muted text-xs">
                  {{ u.last_login_at ? new Date(u.last_login_at).toLocaleString('zh-CN') : '从未' }}
                </td>
              </tr>
              <tr v-if="users.length === 0">
                <td colspan="6" class="px-4 py-10 text-center text-text-muted">暂无用户</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: Role / Permission Management (superadmin only) -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'roles'" class="flex-1 flex flex-col p-6 overflow-hidden">
        <div class="flex items-center justify-between mb-4 shrink-0">
          <div>
            <h1 class="text-lg font-bold text-text-primary">🛡️ 权限管理</h1>
            <p class="text-xs text-text-muted mt-0.5">设置用户角色：普通用户 / 管理员 / 超级管理员</p>
          </div>
          <button
            class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
            @click="loadUsers"
          >
            🔄 刷新
          </button>
        </div>

        <div v-if="loading" class="flex-1 flex items-center justify-center text-text-muted">
          <div class="flex items-center gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>
        </div>
        <div v-else-if="error" class="flex-1 flex items-center justify-center text-red-400">{{ error }}</div>

        <div v-else class="flex-1 overflow-auto rounded-xl bg-bg-card border border-border">
          <!-- Info banner -->
          <div class="px-4 py-3 bg-amber-500/5 border-b border-amber-500/20 flex items-center gap-2">
            <span class="text-amber-400 text-sm">⚠️</span>
            <span class="text-xs text-amber-400/80">仅超级管理员可修改角色权限，请谨慎操作</span>
          </div>
          <table class="w-full text-sm">
            <thead class="sticky top-0 z-10">
              <tr class="bg-bg-sidebar border-b border-border">
                <th class="text-left px-4 py-3 font-medium text-text-muted">ID</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">用户名</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">当前角色</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">等级</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">修改角色</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">注册时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="u in users"
                :key="u.id"
                class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors"
              >
                <td class="px-4 py-3 text-text-muted font-mono text-xs">{{ u.id }}</td>
                <td class="px-4 py-3 text-text-primary font-medium">
                  {{ u.username }}
                  <span
                    v-if="currentUser?.id === u.id"
                    class="ml-1 text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded-full"
                  >我</span>
                </td>
                <td class="px-4 py-3">
                  <span
                    class="px-2 py-0.5 rounded-full text-xs"
                    :class="roleBadgeClass(u.role)"
                  >
                    {{ roleLabel(u.role) }}
                  </span>
                </td>
                <td class="px-4 py-3 text-text-secondary text-xs">{{ tierLabel(u.tier) }}</td>
                <td class="px-4 py-3">
                  <select
                    v-if="currentUser?.id !== u.id"
                    :value="u.role"
                    :disabled="savingUserId === u.id"
                    class="px-3 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-amber-500/50 cursor-pointer disabled:opacity-60 transition-all"
                    @change="onRoleChange(u, $event)"
                  >
                    <option v-for="opt in roleOptions" :key="opt.value" :value="opt.value">
                      {{ opt.label }}
                    </option>
                  </select>
                  <span v-else class="text-xs text-text-muted italic">— 无法修改自己</span>
                </td>
                <td class="px-4 py-3 text-text-muted text-xs">
                  {{ u.created_at ? new Date(u.created_at).toLocaleString('zh-CN') : '-' }}
                </td>
              </tr>
              <tr v-if="users.length === 0">
                <td colspan="6" class="px-4 py-10 text-center text-text-muted">暂无用户</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Role description cards -->
        <div class="grid grid-cols-3 gap-3 mt-4 shrink-0">
          <div class="rounded-xl bg-bg-card border border-border p-4">
            <div class="flex items-center gap-2 mb-2">
              <span class="px-2 py-0.5 rounded-full text-xs bg-bg-elevated text-text-secondary">普通用户</span>
            </div>
            <p class="text-[11px] text-text-muted leading-relaxed">仅可浏览论文、使用知识库等基础功能</p>
          </div>
          <div class="rounded-xl bg-bg-card border border-blue-500/20 p-4">
            <div class="flex items-center gap-2 mb-2">
              <span class="px-2 py-0.5 rounded-full text-xs bg-blue-500/20 text-blue-400 border border-blue-500/30">管理员</span>
            </div>
            <p class="text-[11px] text-text-muted leading-relaxed">可管理用户等级、执行脚本、配置定时调度</p>
          </div>
          <div class="rounded-xl bg-bg-card border border-amber-500/20 p-4">
            <div class="flex items-center gap-2 mb-2">
              <span class="px-2 py-0.5 rounded-full text-xs bg-amber-500/20 text-amber-400 border border-amber-500/30">超级管理员</span>
            </div>
            <p class="text-[11px] text-text-muted leading-relaxed">拥有所有管理权限，可修改任意用户角色</p>
          </div>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: Pipeline Execution -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'pipeline'" class="flex-1 flex flex-col p-6 gap-4 overflow-auto">
        <div class="shrink-0">
          <h1 class="text-lg font-bold text-text-primary">🚀 脚本执行</h1>
          <p class="text-xs text-text-muted mt-0.5">手动触发 Pipeline 运行，查看实时日志</p>
        </div>

        <!-- Run Controls -->
        <div class="rounded-xl bg-bg-card border border-border p-5">
          <h2 class="text-sm font-semibold text-text-primary mb-3">执行参数</h2>

          <!-- 基础参数 -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
            <div>
              <label class="block text-xs text-text-muted mb-1">运行日期</label>
              <input
                v-model="runDate"
                type="date"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Pipeline</label>
              <select
                v-model="runPipelineName"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option value="default">default (全流程)</option>
                <option value="daily">daily (每日流程)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">摘要模型 (SLLM)</label>
              <select
                v-model="runSllm"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option :value="null">默认</option>
                <option :value="1">1 - Qwen</option>
                <option :value="2">2 - Claude (GPTGod)</option>
                <option :value="3">3 - Claude (VectorEngine)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Zotero 推送</label>
              <select
                v-model="runZo"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option value="F">关闭</option>
                <option value="T">开启</option>
              </select>
            </div>
          </div>

          <!-- Arxiv 检索参数折叠区 -->
          <div class="mb-4">
            <button
              type="button"
              class="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors mb-2"
              @click="showAdvancedParams = !showAdvancedParams"
            >
              <span class="transition-transform duration-200" :class="showAdvancedParams ? 'rotate-90' : ''">▶</span>
              <span>Arxiv 检索参数</span>
              <span
                v-if="runDays || runCategories || runQuery || runMaxPapers"
                class="ml-1 px-1.5 py-0.5 rounded text-[10px] bg-blue-500/20 text-blue-400"
              >已自定义</span>
            </button>

            <div v-if="showAdvancedParams" class="grid grid-cols-2 md:grid-cols-4 gap-3 pl-0">
              <div>
                <label class="block text-xs text-text-muted mb-1">
                  时间窗口 (天)
                  <span class="ml-1 text-[10px] text-text-muted/60">--days，默认 1</span>
                </label>
                <input
                  v-model.number="runDays"
                  type="number"
                  min="1"
                  max="30"
                  placeholder="1"
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 placeholder:text-text-muted/40"
                />
              </div>
              <div>
                <label class="block text-xs text-text-muted mb-1">
                  最大论文数
                  <span class="ml-1 text-[10px] text-text-muted/60">--max-papers，默认 500</span>
                </label>
                <input
                  v-model.number="runMaxPapers"
                  type="number"
                  min="1"
                  max="5000"
                  placeholder="500"
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 placeholder:text-text-muted/40"
                />
              </div>
              <div class="md:col-span-2">
                <label class="block text-xs text-text-muted mb-1">
                  检索分类
                  <span class="ml-1 text-[10px] text-text-muted/60">--categories，逗号分隔，如 cs.AI,cs.LG</span>
                </label>
                <input
                  v-model="runCategories"
                  type="text"
                  placeholder="cs.CL,cs.LG,cs.AI,stat.ML"
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 placeholder:text-text-muted/40"
                />
              </div>
              <div class="md:col-span-4">
                <label class="block text-xs text-text-muted mb-1">
                  附加关键词
                  <span class="ml-1 text-[10px] text-text-muted/60">--query，支持自然语言或 arXiv 高级表达式（ti:/abs:/AND/OR...）</span>
                </label>
                <input
                  v-model="runQuery"
                  type="text"
                  placeholder='例：reinforcement learning 或 ti:"large language model" AND abs:reasoning'
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50 placeholder:text-text-muted/40"
                />
              </div>
            </div>
          </div>

          <div class="flex items-center gap-3">
            <button
              :disabled="isRunning || pipelineLoading"
              class="px-5 py-2 rounded-lg text-sm font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              :class="isRunning
                ? 'bg-gray-600 text-gray-300'
                : 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-600/20'"
              @click="handleRunPipeline"
            >
              {{ pipelineLoading ? '启动中...' : isRunning ? '运行中...' : '▶ 开始执行' }}
            </button>
            <button
              v-if="isRunning"
              class="px-5 py-2 rounded-lg bg-red-600/20 text-red-400 border border-red-500/30 text-sm font-medium hover:bg-red-600/30 transition-all duration-200"
              @click="handleStopPipeline"
            >
              ■ 终止
            </button>
            <button
              v-if="!isRunning && pipelineStatus"
              class="px-3 py-2 rounded-lg border border-border text-xs text-text-secondary bg-transparent hover:bg-bg-hover transition-colors"
              @click="loadPipelineStatus"
            >
              🔄 刷新状态
            </button>
            <span v-if="pipelineError" class="text-red-400 text-sm">{{ pipelineError }}</span>
          </div>
        </div>

        <!-- Status Panel -->
        <div class="rounded-xl bg-bg-card border border-border p-5">
          <h2 class="text-sm font-semibold text-text-primary mb-3">📊 运行状态</h2>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div class="rounded-lg bg-bg-elevated p-3">
              <div class="text-xs text-text-muted mb-1">状态</div>
              <div class="text-sm font-semibold flex items-center gap-2" :class="statusColor">
                <span
                  v-if="isRunning"
                  class="inline-block w-2 h-2 bg-blue-400 rounded-full animate-pulse"
                ></span>
                {{ statusLabel }}
              </div>
            </div>
            <div class="rounded-lg bg-bg-elevated p-3">
              <div class="text-xs text-text-muted mb-1">当前步骤</div>
              <div class="text-sm text-text-primary truncate">{{ pipelineStatus?.current_step || '-' }}</div>
            </div>
            <div class="rounded-lg bg-bg-elevated p-3">
              <div class="text-xs text-text-muted mb-1">开始时间</div>
              <div class="text-sm text-text-primary">{{ formattedStartedAt }}</div>
            </div>
            <div class="rounded-lg bg-bg-elevated p-3">
              <div class="text-xs text-text-muted mb-1">完成时间</div>
              <div class="text-sm text-text-primary">{{ formattedFinishedAt }}</div>
            </div>
          </div>

          <!-- Logs -->
          <div class="mt-3">
            <div class="text-xs text-text-muted mb-2">运行日志</div>
            <div
              ref="logsContainer"
              class="h-64 overflow-auto rounded-lg bg-[#0d1117] border border-border p-3 font-mono text-xs leading-5 text-green-400/90"
            >
              <div v-if="!pipelineStatus?.logs?.length" class="text-text-muted italic">暂无日志...</div>
              <div v-for="(line, i) in pipelineStatus?.logs" :key="i" class="whitespace-pre-wrap break-all">
                <span v-if="line.includes('[ERROR]')" class="text-red-400">{{ line }}</span>
                <span v-else-if="line.includes('SKIP')" class="text-yellow-500/80">{{ line }}</span>
                <span v-else-if="line.includes('RUN step')" class="text-cyan-400">{{ line }}</span>
                <span v-else-if="line.includes('START pipeline')" class="text-blue-400 font-bold">{{ line }}</span>
                <span v-else>{{ line }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: Schedule Config -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'schedule'" class="flex-1 flex flex-col p-6 gap-4 overflow-auto">
        <div class="shrink-0">
          <h1 class="text-lg font-bold text-text-primary">🕐 定时调度</h1>
          <p class="text-xs text-text-muted mt-0.5">配置每日自动执行 Pipeline 的时间和参数</p>
        </div>

        <div class="rounded-xl bg-bg-card border border-border p-5">
          <!-- Toggle -->
          <div class="flex items-center gap-3 mb-5">
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                v-model="schedule.enabled"
                type="checkbox"
                class="sr-only peer"
              />
              <div class="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
            </label>
            <span class="text-sm font-medium" :class="schedule.enabled ? 'text-blue-400' : 'text-text-muted'">
              {{ schedule.enabled ? '已启用自动定时执行' : '自动定时执行已关闭' }}
            </span>
          </div>

          <!-- Config grid -->
          <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
            <div>
              <label class="block text-xs text-text-muted mb-1">执行时间 (时)</label>
              <input
                v-model.number="schedule.hour"
                type="number"
                min="0"
                max="23"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">执行时间 (分)</label>
              <input
                v-model.number="schedule.minute"
                type="number"
                min="0"
                max="59"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Pipeline</label>
              <select
                v-model="schedule.pipeline"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option value="default">default</option>
                <option value="daily">daily</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">摘要模型</label>
              <select
                v-model="schedule.sllm"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option :value="null">默认</option>
                <option :value="1">1 - Qwen</option>
                <option :value="2">2 - Claude (GPTGod)</option>
                <option :value="3">3 - Claude (VectorEngine)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Zotero</label>
              <select
                v-model="schedule.zo"
                class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
              >
                <option value="F">关闭</option>
                <option value="T">开启</option>
              </select>
            </div>
          </div>

          <!-- Summary & Save -->
          <div class="flex items-center gap-3 pt-3 border-t border-border">
            <button
              :disabled="scheduleSaving"
              class="px-5 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white text-sm font-medium shadow-lg shadow-green-600/20 transition-all duration-200 disabled:opacity-50"
              @click="handleSaveSchedule"
            >
              {{ scheduleSaving ? '保存中...' : '💾 保存配置' }}
            </button>
            <span v-if="schedule.enabled" class="text-xs text-text-muted">
              每天 {{ String(schedule.hour).padStart(2, '0') }}:{{ String(schedule.minute).padStart(2, '0') }} 自动执行
              <template v-if="schedule.last_run_date">
                · 上次运行: {{ schedule.last_run_date }}
              </template>
            </span>
          </div>
        </div>

        <!-- Info card -->
        <div class="rounded-xl bg-blue-500/5 border border-blue-500/20 p-4">
          <h3 class="text-sm font-medium text-blue-400 mb-2">💡 说明</h3>
          <ul class="text-xs text-text-muted space-y-1.5 list-none p-0 m-0">
            <li>• 定时调度会在每天设定时间自动执行一次 Pipeline</li>
            <li>• 自动执行期间仍可手动点击「脚本执行」运行，但不会同时执行两个</li>
            <li>• 调度配置会持久化保存，服务重启后自动恢复</li>
            <li>• 如果当天的 Pipeline 输出已存在，对应步骤会自动跳过</li>
          </ul>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: System Config (Redesigned with Preset Selectors) -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'config'" class="flex-1 overflow-auto p-6">
        <div class="max-w-3xl mx-auto space-y-5">
        <!-- Header -->
        <div class="flex items-center justify-between shrink-0">
          <div>
            <h1 class="text-lg font-bold text-text-primary">⚙️ 系统配置</h1>
            <p class="text-xs text-text-muted mt-0.5">选择已存储的模型/提示词配置并应用到各功能角色，直接编辑并保存字数上限</p>
          </div>
          <div class="flex items-center gap-3">
            <span v-if="sysConfigSuccessMsg" class="text-xs text-green-400 flex items-center gap-1.5">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
              {{ sysConfigSuccessMsg }}
            </span>
            <button
              class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="async () => { await Promise.all([loadSystemConfig(), loadLlmConfigs(), loadPromptConfigs()]); detectLlmSelections(); detectPromptSelections(); initWordLimits(); initMineruToken() }"
            >
              🔄 刷新
            </button>
          </div>
        </div>

        <!-- Global loading / error -->
        <div v-if="configLoading" class="flex items-center justify-center py-16 text-text-muted">
          <span class="inline-block w-5 h-5 border-2 border-text-muted border-t-transparent rounded-full animate-spin mr-2"></span>
            加载中...
          </div>
        <div v-else-if="configError" class="text-red-400 text-sm py-4">{{ configError }}</div>

        <template v-else>
          <!-- ===== 快捷入口（无配置时引导） ===== -->
          <div v-if="llmConfigs.length === 0 || promptConfigs.length === 0" class="flex gap-3">
            <div
              v-if="llmConfigs.length === 0"
              class="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl border border-dashed border-border bg-bg-card text-xs text-text-muted"
            >
              <span class="text-base shrink-0">🤖</span>
              <span class="flex-1">尚未创建任何模型配置</span>
              <button
                class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors shrink-0"
                @click="activeTab = 'llm-config'"
              >➕ 创建模型配置</button>
            </div>
            <div
              v-if="promptConfigs.length === 0"
              class="flex-1 flex items-center gap-3 px-4 py-3 rounded-xl border border-dashed border-border bg-bg-card text-xs text-text-muted"
            >
              <span class="text-base shrink-0">📝</span>
              <span class="flex-1">尚未创建任何提示词配置</span>
              <button
                class="px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium transition-colors shrink-0"
                @click="activeTab = 'prompt-config'"
              >➕ 创建提示词</button>
            </div>
          </div>

          <!-- ===== MinerU Token ===== -->
          <div class="rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">🔑</span>
              <div class="flex-1 min-w-0">
                <h2 class="text-sm font-semibold text-text-primary">MinerU Token</h2>
                <p class="text-[11px] text-text-muted">用于 PDF 解析的 MinerU 服务凭证，在 mineru.net/apiManage/token 申请</p>
              </div>
            </div>
            <div class="px-5 py-4 flex items-center gap-2">
              <div class="relative flex-1">
                <input
                  v-model="mineruTokenValue"
                  :type="mineruTokenVisible ? 'text' : 'password'"
                  placeholder="请输入 MinerU Token"
                  class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-colors pr-10 font-mono"
                />
                <button
                  class="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors text-xs select-none"
                  @click="mineruTokenVisible = !mineruTokenVisible"
                >{{ mineruTokenVisible ? '🙈' : '👁' }}</button>
              </div>
              <button
                :disabled="savingMineruToken"
                class="shrink-0 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
                @click="handleSaveMineruToken"
              >{{ savingMineruToken ? '保存中…' : '💾 保存' }}</button>
            </div>
          </div>

          <!-- ===== 功能模块卡片 ===== -->
          <div v-for="mod in configModules" :key="mod.key" class="rounded-xl bg-bg-card border border-border overflow-hidden">
            <!-- Module header -->
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">{{ mod.icon }}</span>
              <div class="flex-1 min-w-0">
                <h2 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h2>
                <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
              </div>
            </div>

            <div class="divide-y divide-border/50">
              <!-- LLM row -->
              <div v-if="mod.llmPrefix" class="px-5 py-3.5 flex items-center gap-3">
                <div class="w-32 shrink-0 flex items-center gap-1.5">
                  <span class="text-sm">🤖</span>
                  <span class="text-xs font-medium text-text-secondary">调用模型</span>
                </div>

                <div class="flex-1 min-w-0">
                  <div v-if="selectedLlmConfigIds[mod.llmPrefix]" class="flex items-center gap-1.5 text-xs">
                    <span class="w-1.5 h-1.5 rounded-full bg-green-400 shrink-0"></span>
                    <span class="font-medium text-text-secondary">{{ llmConfigs.find(c => c.id === selectedLlmConfigIds[mod.llmPrefix])?.name || '—' }}</span>
                    <span class="text-text-muted truncate">· {{ configValues[prefixModelKey[mod.llmPrefix]] }}</span>
                  </div>
                  <div v-else class="text-[11px] text-text-muted italic">
                    {{ llmConfigs.length === 0 ? '暂无模型配置' : '未匹配到已存储配置' }}
                  </div>
                </div>

                <select
                  v-model="selectedLlmConfigIds[mod.llmPrefix]"
                  class="w-40 px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-xs focus:outline-none focus:ring-1 focus:ring-blue-500/50 cursor-pointer"
                >
                  <option :value="null">— 选择配置 —</option>
                  <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>

                <button
                  :disabled="!selectedLlmConfigIds[mod.llmPrefix] || applyingModelPrefix === mod.llmPrefix"
                  class="shrink-0 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  @click="handleApplyLlmConfig(mod.llmPrefix!)"
                >
                  {{ applyingModelPrefix === mod.llmPrefix ? '应用中…' : '应用' }}
                </button>
              </div>

              <!-- Prompt rows -->
              <div v-for="prompt in mod.prompts" :key="prompt.variable" class="px-5 py-3.5 flex items-center gap-3">
                <div class="w-32 shrink-0 flex items-center gap-1.5">
                  <span class="text-sm">📝</span>
                  <span class="text-xs font-medium text-text-secondary">{{ prompt.label }}</span>
                </div>

                <div class="flex-1 min-w-0">
                  <div v-if="selectedPromptConfigIds[prompt.variable]" class="flex items-center gap-1.5 text-xs">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0"></span>
                    <span class="font-medium text-text-secondary">{{ promptConfigs.find(c => c.id === selectedPromptConfigIds[prompt.variable])?.name || '—' }}</span>
                  </div>
                  <div v-else class="text-[11px] text-text-muted italic">
                    {{ promptConfigs.length === 0 ? '暂无提示词配置' : '未匹配到已存储配置' }}
                  </div>
                </div>

                <select
                  v-model="selectedPromptConfigIds[prompt.variable]"
                  class="w-40 px-2.5 py-1.5 rounded-lg bg-bg-elevated border border-border text-text-primary text-xs focus:outline-none focus:ring-1 focus:ring-purple-500/50 cursor-pointer"
                >
                  <option :value="null">— 选择配置 —</option>
                  <option v-for="cfg in promptConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
                </select>

                <button
                  :disabled="!selectedPromptConfigIds[prompt.variable] || applyingPromptVariable === prompt.variable"
                  class="shrink-0 px-3.5 py-1.5 rounded-lg text-xs font-medium bg-purple-600 hover:bg-purple-500 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  @click="handleApplyPromptConfig(prompt.variable)"
                >
                  {{ applyingPromptVariable === prompt.variable ? '应用中…' : '应用' }}
                </button>
              </div>
            </div>
          </div>

          <!-- ===== 字数上限配置 ===== -->
          <div class="rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center justify-between">
              <div class="flex items-center gap-3">
                <span class="text-base leading-none">📏</span>
                <div>
                  <h2 class="text-sm font-semibold text-text-primary">字数上限配置</h2>
                  <p class="text-[11px] text-text-muted">控制摘要各部分的字数上限（按去空白字符计），超出则调用模型压缩</p>
                </div>
              </div>
              <button
                :disabled="savingWordLimits"
                class="px-4 py-1.5 rounded-lg bg-green-600 hover:bg-green-500 text-white text-xs font-medium transition-colors disabled:opacity-50 shrink-0"
                @click="handleSaveWordLimits"
              >
                {{ savingWordLimits ? '保存中...' : '💾 保存' }}
              </button>
            </div>
            <div class="p-5">
              <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                <div v-for="(defaultVal, key) in wordLimitDefaults" :key="key">
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">{{ wordLimitLabels[key] }}</label>
                  <div class="flex items-center gap-1.5">
                    <input
                      v-model.number="wordLimitValues[key]"
                      type="number"
                      step="10"
                      min="10"
                      class="flex-1 min-w-0 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500/50 transition-colors"
                    />
                    <button
                      v-if="wordLimitValues[key] !== defaultVal"
                      class="shrink-0 px-2 py-1.5 rounded text-[11px] border border-border text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors"
                      title="重置为默认值"
                      @click="wordLimitValues[key] = defaultVal"
                    >↺</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaultVal }}</p>
                </div>
              </div>
            </div>
          </div>
        </template>
        </div><!-- /max-w-3xl -->
      </div>

      <!-- ============================================================= -->
      <!-- Page: LLM Config Management -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'llm-config'" class="flex-1 flex flex-col p-6 gap-4 overflow-auto">
        <div class="shrink-0 flex items-center justify-between">
          <div>
            <h1 class="text-lg font-bold text-text-primary">🤖 模型配置管理</h1>
            <p class="text-xs text-text-muted mt-0.5">管理大模型配置，支持应用到不同功能模块</p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="loadLlmConfigs"
            >
              🔄 刷新
            </button>
            <button
              class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
              @click="startEditLlmConfig()"
            >
              ➕ 新建配置
            </button>
          </div>
        </div>

        <div v-if="llmConfigLoading" class="flex-1 flex items-center justify-center text-text-muted">
          <div class="flex items-center gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>
        </div>
        <div v-else-if="llmConfigError" class="flex-1 flex items-center justify-center text-red-400">{{ llmConfigError }}</div>

        <!-- Edit Form -->
        <div v-if="llmConfigEditing !== null || Object.keys(llmConfigForm).length > 0" class="rounded-xl bg-bg-card border border-border p-5 shrink-0">
          <h2 class="text-sm font-semibold text-text-primary mb-4">{{ llmConfigEditing?.id ? '编辑配置' : '新建配置' }}</h2>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs text-text-muted mb-1">配置名称 *</label>
              <input v-model="llmConfigForm.name" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">备注</label>
              <input v-model="llmConfigForm.remark" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Base URL *</label>
              <input v-model="llmConfigForm.base_url" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm font-mono" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">API Key *</label>
              <input v-model="llmConfigForm.api_key" type="password" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm font-mono" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Model *</label>
              <input v-model="llmConfigForm.model" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Max Tokens</label>
              <input v-model.number="llmConfigForm.max_tokens" type="number" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Temperature</label>
              <input v-model.number="llmConfigForm.temperature" type="number" step="0.1" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Concurrency</label>
              <input v-model.number="llmConfigForm.concurrency" type="number" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Input Hard Limit</label>
              <input v-model.number="llmConfigForm.input_hard_limit" type="number" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Input Safety Margin</label>
              <input v-model.number="llmConfigForm.input_safety_margin" type="number" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Endpoint</label>
              <input v-model="llmConfigForm.endpoint" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Completion Window</label>
              <input v-model="llmConfigForm.completion_window" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">Out Root</label>
              <input v-model="llmConfigForm.out_root" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">JSONL Root</label>
              <input v-model="llmConfigForm.jsonl_root" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
          </div>
          <div class="flex items-center gap-2 mt-4">
            <button
              :disabled="llmConfigSaving"
              class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-50"
              @click="saveLlmConfig"
            >
              {{ llmConfigSaving ? '保存中...' : '💾 保存' }}
            </button>
            <button
              class="px-4 py-2 rounded-lg bg-bg-elevated border border-border text-text-secondary text-sm font-medium hover:bg-bg-hover"
              @click="llmConfigEditing = null; llmConfigForm = {}"
            >
              取消
            </button>
          </div>
        </div>

        <!-- Config List -->
        <div v-else class="flex-1 overflow-auto rounded-xl bg-bg-card border border-border">
          <table class="w-full text-sm">
            <thead class="sticky top-0 z-10">
              <tr class="bg-bg-sidebar border-b border-border">
                <th class="text-left px-4 py-3 font-medium text-text-muted">ID</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">名称</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">Base URL</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">Model</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="config in llmConfigs" :key="config.id" class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors">
                <td class="px-4 py-3 text-text-muted font-mono text-xs">{{ config.id }}</td>
                <td class="px-4 py-3 text-text-primary font-medium">{{ config.name }}</td>
                <td class="px-4 py-3 text-text-secondary text-xs font-mono truncate max-w-[200px]">{{ config.base_url }}</td>
                <td class="px-4 py-3 text-text-secondary text-xs">{{ config.model }}</td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <select
                      :disabled="llmConfigApplying === config.id"
                      class="px-2 py-1 rounded bg-bg-elevated border border-border text-text-primary text-xs"
                      @change="applyLlmConfigHandler(config.id, ($event.target as HTMLSelectElement).value)"
                    >
                      <option value="">应用到...</option>
                      <option v-for="opt in usagePrefixOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                    </select>
                    <button
                      class="px-2 py-1 rounded bg-blue-500/20 text-blue-400 text-xs hover:bg-blue-500/30"
                      @click="startEditLlmConfig(config)"
                    >
                      编辑
                    </button>
                    <button
                      class="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs hover:bg-red-500/30"
                      @click="deleteLlmConfigHandler(config.id)"
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="llmConfigs.length === 0">
                <td colspan="5" class="px-4 py-10 text-center text-text-muted">暂无配置</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ============================================================= -->
      <!-- Page: Prompt Config Management -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'prompt-config'" class="flex-1 flex flex-col p-6 gap-4 overflow-auto">
        <div class="shrink-0 flex items-center justify-between">
          <div>
            <h1 class="text-lg font-bold text-text-primary">📝 提示词配置管理</h1>
            <p class="text-xs text-text-muted mt-0.5">管理提示词配置，支持应用到不同功能模块</p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="loadPromptConfigs"
            >
              🔄 刷新
            </button>
            <button
              class="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium transition-colors"
              @click="startEditPromptConfig()"
            >
              ➕ 新建配置
            </button>
          </div>
        </div>

        <div v-if="promptConfigLoading" class="flex-1 flex items-center justify-center text-text-muted">
          <div class="flex items-center gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>
        </div>
        <div v-else-if="promptConfigError" class="flex-1 flex items-center justify-center text-red-400">{{ promptConfigError }}</div>

        <!-- Edit Form -->
        <div v-if="promptConfigEditing !== null || Object.keys(promptConfigForm).length > 0" class="rounded-xl bg-bg-card border border-border p-5 shrink-0">
          <h2 class="text-sm font-semibold text-text-primary mb-4">{{ promptConfigEditing?.id ? '编辑配置' : '新建配置' }}</h2>
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div>
              <label class="block text-xs text-text-muted mb-1">配置名称 *</label>
              <input v-model="promptConfigForm.name" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
            <div>
              <label class="block text-xs text-text-muted mb-1">备注</label>
              <input v-model="promptConfigForm.remark" type="text" class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm" />
            </div>
          </div>
          <div>
            <label class="block text-xs text-text-muted mb-1">提示词内容 *</label>
            <textarea
              v-model="promptConfigForm.prompt_content"
              class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm font-mono resize-y min-h-[200px]"
            />
          </div>
          <div class="flex items-center gap-2 mt-4">
            <button
              :disabled="promptConfigSaving"
              class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-50"
              @click="savePromptConfig"
            >
              {{ promptConfigSaving ? '保存中...' : '💾 保存' }}
            </button>
            <button
              class="px-4 py-2 rounded-lg bg-bg-elevated border border-border text-text-secondary text-sm font-medium hover:bg-bg-hover"
              @click="promptConfigEditing = null; promptConfigForm = {}"
            >
              取消
            </button>
          </div>
        </div>

        <!-- Config List -->
        <div v-else class="flex-1 overflow-auto rounded-xl bg-bg-card border border-border">
          <table class="w-full text-sm">
            <thead class="sticky top-0 z-10">
              <tr class="bg-bg-sidebar border-b border-border">
                <th class="text-left px-4 py-3 font-medium text-text-muted">ID</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">名称</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">内容预览</th>
                <th class="text-left px-4 py-3 font-medium text-text-muted">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="config in promptConfigs" :key="config.id" class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors">
                <td class="px-4 py-3 text-text-muted font-mono text-xs">{{ config.id }}</td>
                <td class="px-4 py-3 text-text-primary font-medium">{{ config.name }}</td>
                <td class="px-4 py-3 text-text-secondary text-xs max-w-[300px] truncate">{{ config.prompt_content.substring(0, 100) }}{{ config.prompt_content.length > 100 ? '...' : '' }}</td>
                <td class="px-4 py-3">
                  <div class="flex items-center gap-2">
                    <select
                      :disabled="promptConfigApplying === config.id"
                      class="px-2 py-1 rounded bg-bg-elevated border border-border text-text-primary text-xs"
                      @change="applyPromptConfigHandler(config.id, ($event.target as HTMLSelectElement).value)"
                    >
                      <option value="">应用到...</option>
                      <option v-for="opt in promptVariableOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                    </select>
                    <button
                      class="px-2 py-1 rounded bg-blue-500/20 text-blue-400 text-xs hover:bg-blue-500/30"
                      @click="startEditPromptConfig(config)"
                    >
                      编辑
                    </button>
                    <button
                      class="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs hover:bg-red-500/30"
                      @click="deletePromptConfigHandler(config.id)"
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="promptConfigs.length === 0">
                <td colspan="4" class="px-4 py-10 text-center text-text-muted">暂无配置</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
