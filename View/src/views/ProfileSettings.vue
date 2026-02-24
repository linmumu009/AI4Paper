<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import {
  fetchUserSettings, saveUserSettings,
  fetchUserLlmPresets, createUserLlmPreset, updateUserLlmPreset, deleteUserLlmPreset,
  fetchUserPromptPresets, createUserPromptPreset, updateUserPromptPreset, deleteUserPromptPreset,
  checkUsername,
} from '../api'
import type { UserLlmPreset, UserPromptPreset } from '../types/paper'
import { currentUser, saveProfile, setPassword, changePassword } from '../stores/auth'

const route = useRoute()

// ---------------------------------------------------------------------------
// Sidebar navigation
// ---------------------------------------------------------------------------

interface NavItem {
  key: string
  label: string
  icon: string
  enabled: boolean
  group: string
}

const navItems: NavItem[] = [
  { key: 'account_info', label: '资料设置', icon: 'user', enabled: true, group: '账号设置' },
  { key: 'llm_presets', label: '模型预设', icon: 'cpu', enabled: true, group: '预设管理' },
  { key: 'prompt_presets', label: '提示词预设', icon: 'scroll', enabled: true, group: '预设管理' },
  { key: 'compare', label: '对比分析', icon: 'compare', enabled: true, group: '功能配置' },
  { key: 'inspiration', label: '灵感涌现', icon: 'lightbulb', enabled: true, group: '功能配置' },
  { key: 'idea_generate', label: '灵感生成', icon: 'zap', enabled: true, group: '功能配置' },
  { key: 'paper_recommend', label: '推荐论文参数', icon: 'star', enabled: true, group: '功能配置' },
  { key: 'paper_summary', label: '论文解读', icon: 'article', enabled: false, group: '功能配置' },
  { key: 'theme_filter', label: '主题筛选', icon: 'filter', enabled: false, group: '功能配置' },
]

const activeNav = ref('account_info')
const showSettingsSidebar = ref(false)

// ---------------------------------------------------------------------------
// Account info / profile state
// ---------------------------------------------------------------------------

const showWelcomeBanner = ref(false)
const profileNickname = ref('')
const profileUsername = ref('')
const profileSaving = ref(false)
const profileSaveSuccess = ref(false)
const profileSaveError = ref('')

const pwdNew = ref('')
const pwdConfirm = ref('')
const pwdOld = ref('')
const pwdSaving = ref(false)
const pwdSuccess = ref(false)
const pwdError = ref('')

// ---------------------------------------------------------------------------
// 实时校验：用户名可用性
// ---------------------------------------------------------------------------
type CheckStatus = 'idle' | 'checking' | 'ok' | 'error'
const usernameCheckStatus = ref<CheckStatus>('idle')
const usernameCheckMsg = ref('')

let _usernameDebounceTimer: ReturnType<typeof setTimeout> | null = null

watch(profileUsername, (val) => {
  if (_usernameDebounceTimer) clearTimeout(_usernameDebounceTimer)
  const trimmed = val.trim()
  // 与当前用户名相同时不检查
  if (trimmed === (currentUser.value?.username || '')) {
    usernameCheckStatus.value = 'idle'
    usernameCheckMsg.value = ''
    return
  }
  if (trimmed.length === 0) {
    usernameCheckStatus.value = 'idle'
    usernameCheckMsg.value = ''
    return
  }
  if (trimmed.length < 3) {
    usernameCheckStatus.value = 'error'
    usernameCheckMsg.value = '至少 3 位'
    return
  }
  usernameCheckStatus.value = 'checking'
  usernameCheckMsg.value = ''
  _usernameDebounceTimer = setTimeout(async () => {
    try {
      const res = await checkUsername(trimmed, currentUser.value?.id)
      if (profileUsername.value.trim() !== trimmed) return // 已过期
      usernameCheckStatus.value = res.available ? 'ok' : 'error'
      usernameCheckMsg.value = res.available ? '' : res.message
    } catch {
      usernameCheckStatus.value = 'idle'
    }
  }, 300)
})

// ---------------------------------------------------------------------------
// 实时校验：密码
// ---------------------------------------------------------------------------
const pwdNewStatus = computed<CheckStatus>(() => {
  if (!pwdNew.value) return 'idle'
  return pwdNew.value.length >= 8 ? 'ok' : 'error'
})
const pwdNewMsg = computed(() => pwdNew.value && pwdNew.value.length < 8 ? '至少 8 位' : '')

const pwdConfirmStatus = computed<CheckStatus>(() => {
  if (!pwdConfirm.value) return 'idle'
  return pwdConfirm.value === pwdNew.value ? 'ok' : 'error'
})
const pwdConfirmMsg = computed(() => pwdConfirm.value && pwdConfirm.value !== pwdNew.value ? '两次密码不一致' : '')

function initProfileForm() {
  profileNickname.value = currentUser.value?.nickname || ''
  profileUsername.value = currentUser.value?.username || ''
  usernameCheckStatus.value = 'idle'
  usernameCheckMsg.value = ''
}

async function handleSaveProfile() {
  profileSaving.value = true
  profileSaveError.value = ''
  profileSaveSuccess.value = false
  try {
    await saveProfile({
      nickname: profileNickname.value.trim() || undefined,
      username: profileUsername.value.trim() || undefined,
    })
    profileSaveSuccess.value = true
    setTimeout(() => { profileSaveSuccess.value = false }, 2500)
  } catch (e: any) {
    profileSaveError.value = e?.response?.data?.detail || e?.message || '保存失败'
  } finally {
    profileSaving.value = false
  }
}

async function handleSetPassword() {
  if (!pwdNew.value) { pwdError.value = '请输入新密码'; return }
  if (pwdNew.value.length < 8) { pwdError.value = '密码至少 8 位'; return }
  if (pwdNew.value !== pwdConfirm.value) { pwdError.value = '两次密码不一致'; return }
  pwdSaving.value = true
  pwdError.value = ''
  pwdSuccess.value = false
  try {
    await setPassword(pwdNew.value)
    pwdNew.value = ''
    pwdConfirm.value = ''
    pwdSuccess.value = true
    setTimeout(() => { pwdSuccess.value = false }, 2500)
  } catch (e: any) {
    pwdError.value = e?.response?.data?.detail || e?.message || '设置失败'
  } finally {
    pwdSaving.value = false
  }
}

async function handleChangePassword() {
  if (!pwdOld.value) { pwdError.value = '请输入旧密码'; return }
  if (!pwdNew.value) { pwdError.value = '请输入新密码'; return }
  if (pwdNew.value.length < 8) { pwdError.value = '新密码至少 8 位'; return }
  if (pwdNew.value !== pwdConfirm.value) { pwdError.value = '两次新密码不一致'; return }
  pwdSaving.value = true
  pwdError.value = ''
  pwdSuccess.value = false
  try {
    await changePassword(pwdOld.value, pwdNew.value)
    pwdOld.value = ''
    pwdNew.value = ''
    pwdConfirm.value = ''
    pwdSuccess.value = true
    setTimeout(() => { pwdSuccess.value = false }, 2500)
  } catch (e: any) {
    pwdError.value = e?.response?.data?.detail || e?.message || '修改失败'
  } finally {
    pwdSaving.value = false
  }
}

// Compute sidebar groups
const navGroups = computed(() => {
  const groups: { name: string; items: NavItem[] }[] = []
  const seen = new Set<string>()
  for (const item of navItems) {
    if (!seen.has(item.group)) {
      seen.add(item.group)
      groups.push({ name: item.group, items: [] })
    }
    groups.find(g => g.name === item.group)!.items.push(item)
  }
  return groups
})

// ---------------------------------------------------------------------------
// Feature Settings state (compare / inspiration)
// ---------------------------------------------------------------------------

const form = reactive<Record<string, any>>({})
const defaults = ref<Record<string, any>>({})
const loading = ref(false)
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')

const showApiKey = ref(false)

// ---------------------------------------------------------------------------
// Load / Save settings
// ---------------------------------------------------------------------------

async function loadSettings(feature: string) {
  loading.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    const res = await fetchUserSettings(feature)
    defaults.value = res.defaults || {}
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, res.settings || {})
  } catch (e: any) {
    saveError.value = e?.message || '加载设置失败'
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  saving.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    const toSave: Record<string, any> = { ...form }
    const res = await saveUserSettings(activeNav.value, toSave)
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, res.settings || {})
    defaults.value = res.defaults || {}
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 2500)
  } catch (e: any) {
    saveError.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

function resetField(key: string) {
  if (key in defaults.value) {
    form[key] = defaults.value[key]
  }
}

// ---------------------------------------------------------------------------
// Computed helpers for feature settings
// ---------------------------------------------------------------------------

const noDefaultKeys = new Set([
  'llm_base_url', 'llm_api_key', 'llm_model', 'llm_preset_id', 'prompt_preset_id',
  // Per-module preset IDs for paper_recommend
  'theme_select_llm_preset_id', 'org_llm_preset_id', 'summary_llm_preset_id', 'summary_limit_llm_preset_id',
  'theme_select_prompt_preset_id', 'org_prompt_preset_id', 'summary_prompt_preset_id',
  'summary_limit_prompt_intro_preset_id', 'summary_limit_prompt_method_preset_id',
  'summary_limit_prompt_findings_preset_id', 'summary_limit_prompt_opinion_preset_id',
  // MinerU 服务密钥
  'mineru_token',
  // Per-phase preset IDs for idea_generate (每阶段独立 1:1)
  'ingest_llm_preset_id',    'ingest_prompt_preset_id',
  'question_llm_preset_id',  'question_prompt_preset_id',
  'candidate_llm_preset_id', 'candidate_prompt_preset_id',
  'review_llm_preset_id',    'review_prompt_preset_id',
  'revise_llm_preset_id',    'revise_prompt_preset_id',
  'plan_llm_preset_id',      'plan_prompt_preset_id',
  'eval_llm_preset_id',      'eval_prompt_preset_id',
])

// Toggle visibility for token-type fields
const mineruTokenVisible = ref(false)

// Module definitions for paper_recommend preset-based config
const recommendModules = [
  {
    key: 'theme_select',
    label: '主题相关性评分',
    icon: '🎯',
    desc: '对论文进行主题相关性评分，筛选相关论文',
    llmFormKey: 'theme_select_llm_preset_id',
    prompts: [
      { formKey: 'theme_select_prompt_preset_id', label: '评分提示词' },
    ],
  },
  {
    key: 'org',
    label: '机构判别',
    icon: '🏛️',
    desc: '提取论文作者机构信息',
    llmFormKey: 'org_llm_preset_id',
    prompts: [
      { formKey: 'org_prompt_preset_id', label: '机构判别提示词' },
    ],
  },
  {
    key: 'summary',
    label: '摘要生成',
    icon: '📄',
    desc: '生成论文中文摘要笔记',
    llmFormKey: 'summary_llm_preset_id',
    prompts: [
      { formKey: 'summary_prompt_preset_id', label: '摘要生成提示词' },
    ],
  },
  {
    key: 'summary_limit',
    label: '摘要精简',
    icon: '✂️',
    desc: '压缩摘要各部分至字数上限（按需触发）',
    llmFormKey: 'summary_limit_llm_preset_id',
    prompts: [
      { formKey: 'summary_limit_prompt_intro_preset_id', label: '文章简介精简提示词' },
      { formKey: 'summary_limit_prompt_method_preset_id', label: '重点思路精简提示词' },
      { formKey: 'summary_limit_prompt_findings_preset_id', label: '分析总结精简提示词' },
      { formKey: 'summary_limit_prompt_opinion_preset_id', label: '个人观点精简提示词' },
    ],
  },
]

// Module definitions for idea_generate preset-based config
const ideaModules = [
  {
    key: 'ingest',
    label: '原子抽取 (idea_ingest)',
    icon: '⚗️',
    desc: '从论文全文中抽取结构化"灵感原子"',
    llmFormKey: 'ingest_llm_preset_id',
    prompts: [
      { formKey: 'ingest_prompt_preset_id', label: '原子抽取提示词' },
    ],
  },
  {
    key: 'question',
    label: '研究问题生成 (idea_question)',
    icon: '❓',
    desc: '从局限性原子挖掘有价值的研究问题',
    llmFormKey: 'question_llm_preset_id',
    prompts: [
      { formKey: 'question_prompt_preset_id', label: '研究问题生成提示词' },
    ],
  },
  {
    key: 'candidate',
    label: '灵感候选生成 (idea_candidate)',
    icon: '💡',
    desc: '基于研究问题与原子生成多策略灵感候选',
    llmFormKey: 'candidate_llm_preset_id',
    prompts: [
      { formKey: 'candidate_prompt_preset_id', label: '灵感候选生成提示词' },
    ],
  },
  {
    key: 'review',
    label: '灵感评审 (idea_review)',
    icon: '🔍',
    desc: '多评委对灵感候选进行评审打分',
    llmFormKey: 'review_llm_preset_id',
    prompts: [
      { formKey: 'review_prompt_preset_id', label: '灵感评审提示词' },
    ],
  },
  {
    key: 'revise',
    label: '灵感修订 (idea_revise)',
    icon: '✏️',
    desc: '根据评审反馈自动修订灵感候选',
    llmFormKey: 'revise_llm_preset_id',
    prompts: [
      { formKey: 'revise_prompt_preset_id', label: '灵感修订提示词' },
    ],
  },
  {
    key: 'plan',
    label: '实验计划生成 (idea_plan)',
    icon: '📋',
    desc: '为通过评审的灵感生成可执行实验计划',
    llmFormKey: 'plan_llm_preset_id',
    prompts: [
      { formKey: 'plan_prompt_preset_id', label: '实验计划生成提示词' },
    ],
  },
  {
    key: 'eval',
    label: '评测回放 (idea_eval)',
    icon: '🔁',
    desc: '对历史问题集重新生成灵感用于版本对比',
    llmFormKey: 'eval_llm_preset_id',
    prompts: [
      { formKey: 'eval_prompt_preset_id', label: '评测回放提示词' },
    ],
  },
]

function hasDefault(key: string): boolean {
  return !noDefaultKeys.has(key) && key in defaults.value
}

function isDefault(key: string): boolean {
  if (!hasDefault(key)) return false
  return form[key] === defaults.value[key]
}

// Determine if user is using a preset or manual config for the current feature
const usePresetMode = computed(() => {
  return !!form.llm_preset_id
})

const usePromptPresetMode = computed(() => {
  return !!form.prompt_preset_id
})

// ---------------------------------------------------------------------------
// LLM Presets state
// ---------------------------------------------------------------------------

const llmPresets = ref<UserLlmPreset[]>([])
const llmPresetsLoading = ref(false)
const llmPresetsError = ref('')

// Editing
const editingLlmPreset = ref<UserLlmPreset | null>(null)
const showLlmForm = ref(false)
const llmForm = reactive({
  name: '',
  base_url: '',
  api_key: '',
  model: '',
  max_tokens: null as number | null,
  temperature: null as number | null,
  input_hard_limit: null as number | null,
  input_safety_margin: null as number | null,
})
const llmFormSaving = ref(false)
const showLlmFormApiKey = ref(false)

async function loadLlmPresets() {
  llmPresetsLoading.value = true
  llmPresetsError.value = ''
  try {
    const res = await fetchUserLlmPresets()
    llmPresets.value = res.presets
  } catch (e: any) {
    llmPresetsError.value = e?.message || '加载模型预设失败'
  } finally {
    llmPresetsLoading.value = false
  }
}

function openLlmForm(preset?: UserLlmPreset) {
  if (preset) {
    editingLlmPreset.value = preset
    llmForm.name = preset.name
    llmForm.base_url = preset.base_url
    llmForm.api_key = preset.api_key
    llmForm.model = preset.model
    llmForm.max_tokens = preset.max_tokens ?? null
    llmForm.temperature = preset.temperature ?? null
    llmForm.input_hard_limit = preset.input_hard_limit ?? null
    llmForm.input_safety_margin = preset.input_safety_margin ?? null
  } else {
    editingLlmPreset.value = null
    llmForm.name = ''
    llmForm.base_url = ''
    llmForm.api_key = ''
    llmForm.model = ''
    llmForm.max_tokens = null
    llmForm.temperature = null
    llmForm.input_hard_limit = null
    llmForm.input_safety_margin = null
  }
  showLlmFormApiKey.value = false
  showLlmForm.value = true
}

function closeLlmForm() {
  showLlmForm.value = false
  editingLlmPreset.value = null
}

async function saveLlmPreset() {
  if (!llmForm.name.trim()) return
  llmFormSaving.value = true
  try {
    const payload: any = {
      name: llmForm.name,
      base_url: llmForm.base_url,
      api_key: llmForm.api_key,
      model: llmForm.model,
      max_tokens: llmForm.max_tokens,
      temperature: llmForm.temperature,
      input_hard_limit: llmForm.input_hard_limit,
      input_safety_margin: llmForm.input_safety_margin,
    }
    if (editingLlmPreset.value) {
      await updateUserLlmPreset(editingLlmPreset.value.id, payload)
    } else {
      await createUserLlmPreset(payload)
    }
    await loadLlmPresets()
    closeLlmForm()
  } catch (e: any) {
    llmPresetsError.value = e?.message || '保存失败'
  } finally {
    llmFormSaving.value = false
  }
}

async function removeLlmPreset(preset: UserLlmPreset) {
  if (!confirm(`确定要删除预设「${preset.name}」吗？`)) return
  try {
    await deleteUserLlmPreset(preset.id)
    await loadLlmPresets()
  } catch (e: any) {
    llmPresetsError.value = e?.message || '删除失败'
  }
}

function maskKey(key: string): string {
  if (!key) return ''
  if (key.length <= 8) return '••••••••'
  return key.slice(0, 4) + '••••' + key.slice(-4)
}

// ---------------------------------------------------------------------------
// Prompt Presets state
// ---------------------------------------------------------------------------

const promptPresets = ref<UserPromptPreset[]>([])
const promptPresetsLoading = ref(false)
const promptPresetsError = ref('')

const editingPromptPreset = ref<UserPromptPreset | null>(null)
const showPromptForm = ref(false)
const promptForm = reactive({
  name: '',
  prompt_content: '',
})
const promptFormSaving = ref(false)

async function loadPromptPresets() {
  promptPresetsLoading.value = true
  promptPresetsError.value = ''
  try {
    const res = await fetchUserPromptPresets()
    promptPresets.value = res.presets
  } catch (e: any) {
    promptPresetsError.value = e?.message || '加载提示词预设失败'
  } finally {
    promptPresetsLoading.value = false
  }
}

function openPromptForm(preset?: UserPromptPreset) {
  if (preset) {
    editingPromptPreset.value = preset
    promptForm.name = preset.name
    promptForm.prompt_content = preset.prompt_content
  } else {
    editingPromptPreset.value = null
    promptForm.name = ''
    promptForm.prompt_content = ''
  }
  showPromptForm.value = true
}

function closePromptForm() {
  showPromptForm.value = false
  editingPromptPreset.value = null
}

async function savePromptPreset() {
  if (!promptForm.name.trim()) return
  promptFormSaving.value = true
  try {
    const payload = {
      name: promptForm.name,
      prompt_content: promptForm.prompt_content,
    }
    if (editingPromptPreset.value) {
      await updateUserPromptPreset(editingPromptPreset.value.id, payload)
    } else {
      await createUserPromptPreset(payload)
    }
    await loadPromptPresets()
    closePromptForm()
  } catch (e: any) {
    promptPresetsError.value = e?.message || '保存失败'
  } finally {
    promptFormSaving.value = false
  }
}

async function removePromptPreset(preset: UserPromptPreset) {
  if (!confirm(`确定要删除预设「${preset.name}」吗？`)) return
  try {
    await deleteUserPromptPreset(preset.id)
    await loadPromptPresets()
  } catch (e: any) {
    promptPresetsError.value = e?.message || '删除失败'
  }
}

// ---------------------------------------------------------------------------
// Feature accent color helper
// ---------------------------------------------------------------------------

function accentColor(feature: string): string {
  if (feature === 'inspiration') return '#f59e0b'
  if (feature === 'idea_generate') return '#f97316'
  if (feature === 'paper_recommend') return '#ec4899'
  return '#8b5cf6'
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  const tabQuery = route.query.tab as string | undefined
  if (tabQuery && navItems.find(i => i.key === tabQuery && i.enabled)) {
    activeNav.value = tabQuery
  }
  if (route.query.welcome === '1') {
    showWelcomeBanner.value = true
  }
  initProfileForm()
  loadLlmPresets()
  loadPromptPresets()
})

watch(activeNav, (feature) => {
  if (feature === 'compare' || feature === 'inspiration' || feature === 'idea_generate' || feature === 'paper_recommend') {
    loadSettings(feature)
  } else if (feature === 'llm_presets') {
    loadLlmPresets()
  } else if (feature === 'prompt_presets') {
    loadPromptPresets()
  } else if (feature === 'account_info') {
    initProfileForm()
  }
})

watch(() => currentUser.value, () => {
  if (activeNav.value === 'account_info') {
    initProfileForm()
  }
})
</script>

<template>
  <div class="h-full flex overflow-hidden relative">

    <!-- Mobile sidebar overlay backdrop -->
    <div
      v-if="showSettingsSidebar"
      class="fixed inset-0 z-20 bg-black/60 md:hidden"
      @click="showSettingsSidebar = false"
    />

    <!-- Mobile settings nav toggle button -->
    <button
      v-if="!showSettingsSidebar"
      class="absolute top-2 left-2 z-10 md:hidden w-8 h-8 flex items-center justify-center rounded-full bg-bg-card border border-border text-text-secondary hover:bg-bg-hover transition-colors"
      title="个人中心导航"
      @click="showSettingsSidebar = true"
    >
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
    </button>

    <!-- ========== Left sidebar navigation ========== -->
    <aside
      :class="[
        'z-30 md:z-auto w-56 h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0 transition-transform duration-300',
        showSettingsSidebar
          ? 'fixed md:relative inset-y-0 left-0 translate-x-0'
          : 'fixed md:relative inset-y-0 left-0 -translate-x-full md:translate-x-0'
      ]"
    >
      <!-- Mobile close button -->
      <button
        class="md:hidden absolute top-3 right-3 w-7 h-7 flex items-center justify-center rounded-full bg-bg-hover text-text-muted hover:text-text-primary border-none cursor-pointer"
        @click="showSettingsSidebar = false"
      >✕</button>
      <!-- Header -->
      <div class="px-4 py-5 border-b border-border">
        <h1 class="text-base font-bold text-text-primary flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          个人中心
        </h1>
        <p class="text-xs text-text-muted mt-1">{{ currentUser?.username }}</p>
      </div>

      <!-- Nav items (grouped) -->
      <nav class="flex-1 overflow-y-auto p-2">
        <div v-for="group in navGroups" :key="group.name" class="mb-1">
          <div class="px-3 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted/60">
            {{ group.name }}
          </div>
          <div class="space-y-0.5">
            <button
              v-for="item in group.items"
              :key="item.key"
              class="w-full px-3 py-2 text-left text-sm flex items-center gap-2.5 rounded-lg transition-all duration-150"
              :class="[
                item.enabled
                  ? (activeNav === item.key
                      ? 'bg-bg-elevated text-text-primary font-medium shadow-sm'
                      : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer')
                  : 'text-text-muted cursor-not-allowed opacity-40',
              ]"
              :disabled="!item.enabled"
              @click="item.enabled && (activeNav = item.key, showSettingsSidebar = false)"
            >
              <!-- Icon: user -->
              <svg v-if="item.icon === 'user'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
              </svg>
              <!-- Icon: cpu -->
              <svg v-else-if="item.icon === 'cpu'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" />
              </svg>
              <!-- Icon: scroll -->
              <svg v-else-if="item.icon === 'scroll'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 0 0-2-2H3a2 2 0 0 0-2 2v3h8" /><path d="M19 17V5a2 2 0 0 0-2-2H4" />
              </svg>
              <!-- Icon: compare -->
              <svg v-else-if="item.icon === 'compare'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
              </svg>
              <!-- Icon: lightbulb -->
              <svg v-else-if="item.icon === 'lightbulb'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18h6" /><path d="M10 22h4" /><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
              </svg>
              <!-- Icon: zap (灵感生成) -->
              <svg v-else-if="item.icon === 'zap'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
              </svg>
              <!-- Icon: star -->
              <svg v-else-if="item.icon === 'star'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
              </svg>
              <!-- Icon: article -->
              <svg v-else-if="item.icon === 'article'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
              </svg>
              <!-- Icon: filter -->
              <svg v-else-if="item.icon === 'filter'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>

              <span class="truncate">{{ item.label }}</span>
              <span v-if="!item.enabled" class="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted shrink-0">即将推出</span>

              <!-- Active indicator -->
              <div v-if="item.enabled && activeNav === item.key" class="ml-auto w-1.5 h-1.5 rounded-full bg-[#8b5cf6] shrink-0"></div>
            </button>
          </div>
        </div>
      </nav>
    </aside>

    <!-- ========== Right content area ========== -->
    <div class="flex-1 h-full overflow-y-auto min-w-0">

      <!-- ============================== -->
      <!-- Account Info page              -->
      <!-- ============================== -->
      <div v-if="activeNav === 'account_info'" class="max-w-2xl mx-auto px-4 sm:px-8 py-6 sm:py-8">

        <!-- Welcome banner for new users -->
        <Transition
          enter-active-class="transition duration-300 ease-out"
          enter-from-class="opacity-0 -translate-y-2"
          enter-to-class="opacity-100 translate-y-0"
          leave-active-class="transition duration-200 ease-in"
          leave-from-class="opacity-100 translate-y-0"
          leave-to-class="opacity-0 -translate-y-2"
        >
          <div v-if="showWelcomeBanner" class="mb-6 rounded-xl bg-gradient-to-r from-[#fd267a]/10 to-[#ff6036]/10 border border-[#fd267a]/20 px-5 py-4 flex items-start gap-3">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#fd267a] shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <div class="flex-1">
              <p class="text-sm font-semibold text-text-primary">欢迎加入！</p>
              <p class="text-xs text-text-muted mt-0.5">你的账号已通过手机号自动创建，建议设置昵称和密码，方便后续使用。</p>
            </div>
            <button class="text-text-muted hover:text-text-primary transition-colors" @click="showWelcomeBanner = false">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </Transition>

        <!-- Page header -->
        <div class="mb-6">
          <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#fd267a]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
            </svg>
            资料设置
          </h2>
          <p class="text-xs text-text-muted mt-1">管理你的个人信息和登录凭证</p>
        </div>

        <!-- ── Section 1: Basic info ── -->
        <section class="mb-6 rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-4">基本信息</h3>

          <div class="space-y-4">
            <!-- Nickname -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">昵称</label>
              <input
                v-model="profileNickname"
                type="text"
                maxlength="64"
                placeholder="设置一个显示昵称（可选）"
                class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
              />
            </div>

            <!-- Username -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">
                用户名
                <span v-if="currentUser?.is_phone_auto_created" class="ml-1.5 text-[#fd267a] text-[10px] font-normal">建议修改</span>
              </label>
              <div class="relative">
                <input
                  v-model="profileUsername"
                  type="text"
                  minlength="3"
                  maxlength="32"
                  placeholder="3-32 位字母/数字/._-"
                  class="w-full px-3 py-2.5 pr-9 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
                  :class="usernameCheckStatus === 'error' ? 'border-red-400/60' : usernameCheckStatus === 'ok' ? 'border-green-400/60' : ''"
                />
                <!-- 检查中 spinner -->
                <span v-if="usernameCheckStatus === 'checking'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-text-muted animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"/>
                  </svg>
                </span>
                <!-- 可用对勾 -->
                <span v-else-if="usernameCheckStatus === 'ok'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-green-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </span>
                <!-- 不可用叉号 -->
                <span v-else-if="usernameCheckStatus === 'error'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </span>
              </div>
              <p v-if="usernameCheckStatus === 'error' && usernameCheckMsg" class="text-[11px] text-red-400 mt-1">{{ usernameCheckMsg }}</p>
              <p v-else-if="currentUser?.is_phone_auto_created" class="text-[10px] text-text-muted mt-1">
                当前用户名为系统自动生成（{{ currentUser?.username }}），建议修改为你自己的用户名
              </p>
            </div>

            <!-- Phone (read-only) -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">绑定手机号</label>
              <div class="flex items-center gap-2 px-3 py-2.5 bg-bg border border-border rounded-lg text-sm text-text-muted">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>
                </svg>
                <span>{{ currentUser?.phone || '未绑定' }}</span>
                <span v-if="currentUser?.phone_verified" class="ml-auto text-[10px] px-1.5 py-0.5 rounded-full bg-green-500/10 text-green-500 font-medium">已验证</span>
              </div>
            </div>
          </div>

          <!-- Save basic info -->
          <div class="mt-5 flex items-center gap-3">
            <button
              class="px-5 py-2 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-[#fd267a] to-[#ff6036] hover:opacity-90 transition-all disabled:opacity-50 cursor-pointer"
              :disabled="profileSaving"
              @click="handleSaveProfile"
            >{{ profileSaving ? '保存中...' : '保存' }}</button>
            <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0" enter-to-class="opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100" leave-to-class="opacity-0">
              <span v-if="profileSaveSuccess" class="text-xs text-green-500 flex items-center gap-1">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                已保存
              </span>
              <span v-else-if="profileSaveError" class="text-xs text-[#fd267a]">{{ profileSaveError }}</span>
            </Transition>
          </div>
        </section>

        <!-- ── Section 2: Password ── -->
        <section class="rounded-xl border border-border bg-bg-card p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-1">密码</h3>
          <p class="text-xs text-text-muted mb-4">
            {{ currentUser?.has_password ? '修改登录密码（需提供旧密码）' : '为账号设置密码，可以使用用户名+密码方式登录' }}
          </p>

          <div class="space-y-3">
            <!-- Old password (only when password exists) -->
            <div v-if="currentUser?.has_password">
              <label class="block text-xs font-medium text-text-secondary mb-1.5">旧密码</label>
              <input
                v-model="pwdOld"
                type="password"
                maxlength="128"
                placeholder="请输入旧密码"
                class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
              />
            </div>

            <!-- New password -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">{{ currentUser?.has_password ? '新密码' : '密码' }}</label>
              <div class="relative">
                <input
                  v-model="pwdNew"
                  type="password"
                  maxlength="128"
                  placeholder="至少 8 位"
                  class="w-full px-3 py-2.5 pr-9 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
                  :class="pwdNewStatus === 'error' ? 'border-red-400/60' : pwdNewStatus === 'ok' ? 'border-green-400/60' : ''"
                />
                <span v-if="pwdNewStatus === 'ok'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-green-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </span>
                <span v-else-if="pwdNewStatus === 'error'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </span>
              </div>
              <p v-if="pwdNewMsg" class="text-[11px] text-red-400 mt-1">{{ pwdNewMsg }}</p>
            </div>

            <!-- Confirm password -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">确认密码</label>
              <div class="relative">
                <input
                  v-model="pwdConfirm"
                  type="password"
                  maxlength="128"
                  placeholder="再次输入密码"
                  class="w-full px-3 py-2.5 pr-9 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#fd267a]/60 transition-colors"
                  :class="pwdConfirmStatus === 'error' ? 'border-red-400/60' : pwdConfirmStatus === 'ok' ? 'border-green-400/60' : ''"
                />
                <span v-if="pwdConfirmStatus === 'ok'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-green-500" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                </span>
                <span v-else-if="pwdConfirmStatus === 'error'" class="absolute right-3 top-1/2 -translate-y-1/2">
                  <svg class="w-4 h-4 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </span>
              </div>
              <p v-if="pwdConfirmMsg" class="text-[11px] text-red-400 mt-1">{{ pwdConfirmMsg }}</p>
            </div>
          </div>

          <div class="mt-5 flex items-center gap-3">
            <button
              class="px-5 py-2 rounded-lg text-sm font-semibold text-white bg-gradient-to-r from-[#fd267a] to-[#ff6036] hover:opacity-90 transition-all disabled:opacity-50 cursor-pointer"
              :disabled="pwdSaving"
              @click="currentUser?.has_password ? handleChangePassword() : handleSetPassword()"
            >{{ pwdSaving ? '保存中...' : (currentUser?.has_password ? '修改密码' : '设置密码') }}</button>
            <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0" enter-to-class="opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100" leave-to-class="opacity-0">
              <span v-if="pwdSuccess" class="text-xs text-green-500 flex items-center gap-1">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                已{{ currentUser?.has_password ? '修改' : '设置' }}
              </span>
              <span v-else-if="pwdError" class="text-xs text-[#fd267a]">{{ pwdError }}</span>
            </Transition>
          </div>
        </section>
      </div>

      <!-- ============================== -->
      <!-- LLM Presets page -->
      <!-- ============================== -->
      <div v-else-if="activeNav === 'llm_presets'" class="max-w-3xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Header -->
        <div class="flex items-center justify-between mb-6">
          <div>
            <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" /><line x1="9" y1="1" x2="9" y2="4" /><line x1="15" y1="1" x2="15" y2="4" /><line x1="9" y1="20" x2="9" y2="23" /><line x1="15" y1="20" x2="15" y2="23" /><line x1="20" y1="9" x2="23" y2="9" /><line x1="20" y1="14" x2="23" y2="14" /><line x1="1" y1="9" x2="4" y2="9" /><line x1="1" y1="14" x2="4" y2="14" />
              </svg>
              模型预设
            </h2>
            <p class="text-xs text-text-muted mt-1">管理你的 LLM 连接预设，在功能配置中快速切换使用</p>
          </div>
          <button
            class="px-4 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] text-white hover:opacity-90 shadow-lg shadow-[#8b5cf6]/20 transition-all flex items-center gap-1.5"
            @click="openLlmForm()"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
            新建预设
          </button>
        </div>

        <!-- Loading -->
        <div v-if="llmPresetsLoading" class="flex items-center justify-center py-20">
          <div class="relative w-10 h-10 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#8b5cf6] animate-spin"></div>
          </div>
        </div>

        <!-- Error -->
        <div v-else-if="llmPresetsError" class="text-center py-20">
          <p class="text-sm text-tinder-pink">{{ llmPresetsError }}</p>
        </div>

        <!-- Empty state -->
        <div v-else-if="llmPresets.length === 0 && !showLlmForm" class="text-center py-20">
          <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[#8b5cf6]/10 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-[#8b5cf6]/50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
            </svg>
          </div>
          <h3 class="text-sm font-semibold text-text-secondary mb-1">还没有模型预设</h3>
          <p class="text-xs text-text-muted mb-4">创建模型预设后，可以在对比分析和灵感涌现中快速选用</p>
          <button
            class="px-4 py-2 rounded-lg text-sm font-medium bg-[#8b5cf6]/10 text-[#8b5cf6] hover:bg-[#8b5cf6]/20 transition-colors"
            @click="openLlmForm()"
          >创建第一个预设</button>
        </div>

        <!-- Preset cards grid -->
        <div v-else-if="!showLlmForm" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div
            v-for="preset in llmPresets"
            :key="preset.id"
            class="group rounded-xl border border-border bg-bg-card p-5 hover:border-[#8b5cf6]/30 hover:shadow-lg hover:shadow-[#8b5cf6]/5 transition-all duration-200"
          >
            <!-- Card header -->
            <div class="flex items-start justify-between mb-3">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-lg bg-gradient-to-br from-[#6366f1]/20 to-[#8b5cf6]/20 flex items-center justify-center shrink-0">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-4.5 h-4.5 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <rect x="4" y="4" width="16" height="16" rx="2" /><rect x="9" y="9" width="6" height="6" />
                  </svg>
                </div>
                <div>
                  <h4 class="text-sm font-semibold text-text-primary leading-tight">{{ preset.name }}</h4>
                  <p class="text-[11px] text-text-muted mt-0.5 font-mono">{{ preset.model || '未设置模型' }}</p>
                </div>
              </div>
              <!-- Actions -->
              <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  class="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
                  title="编辑"
                  @click="openLlmForm(preset)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                </button>
                <button
                  class="p-1.5 rounded-md hover:bg-red-500/10 text-text-muted hover:text-red-400 transition-colors"
                  title="删除"
                  @click="removeLlmPreset(preset)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
                </button>
              </div>
            </div>
            <!-- Card details -->
            <div class="space-y-1.5 text-xs">
              <div class="flex items-center gap-2 text-text-muted">
                <span class="w-14 shrink-0 text-text-muted/60">URL</span>
                <span class="text-text-secondary font-mono truncate">{{ preset.base_url || '—' }}</span>
              </div>
              <div class="flex items-center gap-2 text-text-muted">
                <span class="w-14 shrink-0 text-text-muted/60">Key</span>
                <span class="text-text-secondary font-mono">{{ maskKey(preset.api_key) || '—' }}</span>
              </div>
              <div class="flex items-center gap-2 text-text-muted" v-if="preset.temperature != null">
                <span class="w-14 shrink-0 text-text-muted/60">Temp</span>
                <span class="text-text-secondary">{{ preset.temperature }}</span>
              </div>
              <div class="flex items-center gap-2 text-text-muted" v-if="preset.max_tokens != null">
                <span class="w-14 shrink-0 text-text-muted/60">Tokens</span>
                <span class="text-text-secondary">{{ preset.max_tokens }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- LLM Preset Form (slide-in panel) -->
        <Transition
          enter-active-class="transition duration-200 ease-out"
          enter-from-class="opacity-0 translate-y-2"
          enter-to-class="opacity-100 translate-y-0"
          leave-active-class="transition duration-150 ease-in"
          leave-from-class="opacity-100 translate-y-0"
          leave-to-class="opacity-0 translate-y-2"
        >
          <div v-if="showLlmForm" class="rounded-xl border border-[#8b5cf6]/20 bg-bg-card p-6 shadow-xl shadow-[#8b5cf6]/5">
            <div class="flex items-center justify-between mb-5">
              <h3 class="text-sm font-semibold text-text-primary">
                {{ editingLlmPreset ? '编辑模型预设' : '新建模型预设' }}
              </h3>
              <button class="p-1 rounded-md hover:bg-bg-hover text-text-muted" @click="closeLlmForm">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
              </button>
            </div>

            <div class="space-y-4">
              <!-- Name -->
              <div>
                <label class="block text-xs font-medium text-text-secondary mb-1.5">预设名称 <span class="text-[#8b5cf6]">*</span></label>
                <input
                  v-model="llmForm.name"
                  type="text"
                  placeholder="例如: GPT-4o、Claude Sonnet、通义千问..."
                  class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors"
                />
              </div>

              <!-- URL + Key row -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">API URL</label>
                  <input
                    v-model="llmForm.base_url"
                    type="text"
                    placeholder="https://api.openai.com/v1"
                    class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors font-mono"
                  />
                </div>
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">API Key</label>
                  <div class="relative">
                    <input
                      v-model="llmForm.api_key"
                      :type="showLlmFormApiKey ? 'text' : 'password'"
                      placeholder="sk-..."
                      class="w-full px-3 py-2.5 pr-9 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors font-mono"
                    />
                    <button type="button" class="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary" @click="showLlmFormApiKey = !showLlmFormApiKey">
                      <svg v-if="showLlmFormApiKey" xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
                      <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
                    </button>
                  </div>
                </div>
              </div>

              <!-- Model -->
              <div>
                <label class="block text-xs font-medium text-text-secondary mb-1.5">模型名称</label>
                <input
                  v-model="llmForm.model"
                  type="text"
                  placeholder="gpt-4o / claude-sonnet-4-20250514 / qwen-plus ..."
                  class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors"
                />
              </div>

              <!-- Advanced params row -->
              <details class="group/adv">
                <summary class="text-xs text-text-muted cursor-pointer hover:text-text-secondary transition-colors select-none flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 transition-transform group-open/adv:rotate-90" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6" /></svg>
                  高级参数（可选）
                </summary>
                <div class="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div>
                    <label class="block text-[11px] text-text-muted mb-1">Temperature</label>
                    <input v-model.number="llmForm.temperature" type="number" step="0.1" min="0" max="2" placeholder="1.0" class="w-full px-2.5 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors" />
                  </div>
                  <div>
                    <label class="block text-[11px] text-text-muted mb-1">Max Tokens</label>
                    <input v-model.number="llmForm.max_tokens" type="number" step="256" min="256" placeholder="4096" class="w-full px-2.5 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors" />
                  </div>
                  <div>
                    <label class="block text-[11px] text-text-muted mb-1">Hard Limit</label>
                    <input v-model.number="llmForm.input_hard_limit" type="number" step="1024" placeholder="129024" class="w-full px-2.5 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors" />
                  </div>
                  <div>
                    <label class="block text-[11px] text-text-muted mb-1">Safety Margin</label>
                    <input v-model.number="llmForm.input_safety_margin" type="number" step="256" placeholder="4096" class="w-full px-2.5 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors" />
                  </div>
                </div>
              </details>
            </div>

            <!-- Form actions -->
            <div class="flex items-center justify-end gap-2 mt-6 pt-4 border-t border-border">
              <button
                class="px-4 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover transition-colors"
                @click="closeLlmForm"
              >取消</button>
              <button
                class="px-5 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] text-white hover:opacity-90 shadow-lg shadow-[#8b5cf6]/20 transition-all disabled:opacity-50"
                :disabled="!llmForm.name.trim() || llmFormSaving"
                @click="saveLlmPreset"
              >{{ llmFormSaving ? '保存中...' : '保存预设' }}</button>
            </div>
          </div>
        </Transition>
      </div>

      <!-- ============================== -->
      <!-- Prompt Presets page -->
      <!-- ============================== -->
      <div v-else-if="activeNav === 'prompt_presets'" class="max-w-3xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Header -->
        <div class="flex items-center justify-between mb-6">
          <div>
            <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#10b981]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 0 0-2-2H3a2 2 0 0 0-2 2v3h8" /><path d="M19 17V5a2 2 0 0 0-2-2H4" />
              </svg>
              提示词预设
            </h2>
            <p class="text-xs text-text-muted mt-1">管理你的 System Prompt 预设，在功能配置中快速切换使用</p>
          </div>
          <button
            class="px-4 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-[#059669] to-[#10b981] text-white hover:opacity-90 shadow-lg shadow-[#10b981]/20 transition-all flex items-center gap-1.5"
            @click="openPromptForm()"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
            新建预设
          </button>
        </div>

        <!-- Loading -->
        <div v-if="promptPresetsLoading" class="flex items-center justify-center py-20">
          <div class="relative w-10 h-10 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#10b981] animate-spin"></div>
          </div>
        </div>

        <!-- Error -->
        <div v-else-if="promptPresetsError" class="text-center py-20">
          <p class="text-sm text-tinder-pink">{{ promptPresetsError }}</p>
        </div>

        <!-- Empty state -->
        <div v-else-if="promptPresets.length === 0 && !showPromptForm" class="text-center py-20">
          <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[#10b981]/10 flex items-center justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-8 h-8 text-[#10b981]/50" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 0 0-2-2H3a2 2 0 0 0-2 2v3h8" /><path d="M19 17V5a2 2 0 0 0-2-2H4" />
            </svg>
          </div>
          <h3 class="text-sm font-semibold text-text-secondary mb-1">还没有提示词预设</h3>
          <p class="text-xs text-text-muted mb-4">创建提示词预设后，可以在对比分析和灵感涌现中快速选用</p>
          <button
            class="px-4 py-2 rounded-lg text-sm font-medium bg-[#10b981]/10 text-[#10b981] hover:bg-[#10b981]/20 transition-colors"
            @click="openPromptForm()"
          >创建第一个预设</button>
        </div>

        <!-- Prompt preset cards -->
        <div v-else-if="!showPromptForm" class="space-y-3">
          <div
            v-for="preset in promptPresets"
            :key="preset.id"
            class="group rounded-xl border border-border bg-bg-card p-5 hover:border-[#10b981]/30 hover:shadow-lg hover:shadow-[#10b981]/5 transition-all duration-200"
          >
            <div class="flex items-start justify-between mb-2">
              <div class="flex items-center gap-2.5">
                <div class="w-9 h-9 rounded-lg bg-gradient-to-br from-[#059669]/20 to-[#10b981]/20 flex items-center justify-center shrink-0">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-4.5 h-4.5 text-[#10b981]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M8 21h12a2 2 0 0 0 2-2v-2H10v2a2 2 0 1 1-4 0V5a2 2 0 0 0-2-2H3a2 2 0 0 0-2 2v3h8" /><path d="M19 17V5a2 2 0 0 0-2-2H4" />
                  </svg>
                </div>
                <h4 class="text-sm font-semibold text-text-primary">{{ preset.name }}</h4>
              </div>
              <!-- Actions -->
              <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  class="p-1.5 rounded-md hover:bg-bg-hover text-text-muted hover:text-text-primary transition-colors"
                  title="编辑"
                  @click="openPromptForm(preset)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
                </button>
                <button
                  class="p-1.5 rounded-md hover:bg-red-500/10 text-text-muted hover:text-red-400 transition-colors"
                  title="删除"
                  @click="removePromptPreset(preset)"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
                </button>
              </div>
            </div>
            <p class="text-xs text-text-muted line-clamp-3 font-mono leading-relaxed pl-[46px]">
              {{ preset.prompt_content.substring(0, 200) }}{{ preset.prompt_content.length > 200 ? '...' : '' }}
            </p>
          </div>
        </div>

        <!-- Prompt Preset Form -->
        <Transition
          enter-active-class="transition duration-200 ease-out"
          enter-from-class="opacity-0 translate-y-2"
          enter-to-class="opacity-100 translate-y-0"
          leave-active-class="transition duration-150 ease-in"
          leave-from-class="opacity-100 translate-y-0"
          leave-to-class="opacity-0 translate-y-2"
        >
          <div v-if="showPromptForm" class="rounded-xl border border-[#10b981]/20 bg-bg-card p-6 shadow-xl shadow-[#10b981]/5">
            <div class="flex items-center justify-between mb-5">
              <h3 class="text-sm font-semibold text-text-primary">
                {{ editingPromptPreset ? '编辑提示词预设' : '新建提示词预设' }}
              </h3>
              <button class="p-1 rounded-md hover:bg-bg-hover text-text-muted" @click="closePromptForm">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
              </button>
            </div>

            <div class="space-y-4">
              <div>
                <label class="block text-xs font-medium text-text-secondary mb-1.5">预设名称 <span class="text-[#10b981]">*</span></label>
                <input
                  v-model="promptForm.name"
                  type="text"
                  placeholder="例如: 论文对比、深入分析、简要概括..."
                  class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#10b981] transition-colors"
                />
              </div>
              <div>
                <label class="block text-xs font-medium text-text-secondary mb-1.5">提示词内容</label>
                <textarea
                  v-model="promptForm.prompt_content"
                  rows="14"
                  placeholder="输入系统提示词内容..."
                  class="w-full px-3 py-2.5 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#10b981] transition-colors resize-y leading-relaxed font-mono"
                ></textarea>
              </div>
            </div>

            <!-- Form actions -->
            <div class="flex items-center justify-end gap-2 mt-6 pt-4 border-t border-border">
              <button
                class="px-4 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-hover transition-colors"
                @click="closePromptForm"
              >取消</button>
              <button
                class="px-5 py-2 rounded-lg text-sm font-medium bg-gradient-to-r from-[#059669] to-[#10b981] text-white hover:opacity-90 shadow-lg shadow-[#10b981]/20 transition-all disabled:opacity-50"
                :disabled="!promptForm.name.trim() || promptFormSaving"
                @click="savePromptPreset"
              >{{ promptFormSaving ? '保存中...' : '保存预设' }}</button>
            </div>
          </div>
        </Transition>
      </div>

      <!-- ============================== -->
      <!-- Feature settings: compare / inspiration -->
      <!-- ============================== -->
      <div v-else-if="activeNav === 'compare' || activeNav === 'inspiration'" class="max-w-2xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center h-full min-h-[400px]">
          <div class="text-center">
            <div class="relative w-12 h-12 mx-auto mb-3 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#8b5cf6] border-r-[#6366f1] animate-spin"></div>
            </div>
            <p class="text-sm text-text-muted">加载设置...</p>
          </div>
        </div>

        <template v-else>
          <!-- Section title -->
          <div class="mb-8">
            <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
              <svg v-if="activeNav === 'compare'" xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" :style="{ color: accentColor(activeNav) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
              </svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-5 h-5" :style="{ color: accentColor(activeNav) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18h6" /><path d="M10 22h4" /><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
              </svg>
              {{ activeNav === 'compare' ? '对比分析设置' : activeNav === 'inspiration' ? '灵感涌现设置' : '灵感生成设置' }}
            </h2>
            <p class="text-xs text-text-muted mt-1">
              {{ activeNav === 'compare' ? '配置论文对比分析所使用的大语言模型参数' : activeNav === 'inspiration' ? '配置灵感涌现分析所使用的大语言模型参数' : '配置灵感生成所使用的大语言模型参数' }}
            </p>
          </div>

          <!-- ===== LLM Config Section ===== -->
          <fieldset class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">LLM 连接配置</legend>

            <!-- Preset selector -->
            <div class="mb-5">
              <label class="block text-xs font-medium text-text-secondary mb-2">选择模型预设</label>
              <div class="flex flex-wrap gap-2">
                <!-- "Manual" pill -->
                <button
                  class="px-3 py-1.5 rounded-full text-xs font-medium border transition-all duration-150"
                  :class="!form.llm_preset_id
                    ? `border-transparent text-white shadow-md`
                    : 'border-border text-text-secondary hover:border-text-muted bg-transparent'"
                  :style="!form.llm_preset_id ? { background: `linear-gradient(135deg, #6366f1, ${accentColor(activeNav)})` } : {}"
                  @click="form.llm_preset_id = ''"
                >
                  手动配置
                </button>
                <!-- Preset pills -->
                <button
                  v-for="preset in llmPresets"
                  :key="preset.id"
                  class="px-3 py-1.5 rounded-full text-xs font-medium border transition-all duration-150"
                  :class="String(form.llm_preset_id) === String(preset.id)
                    ? `border-transparent text-white shadow-md`
                    : 'border-border text-text-secondary hover:border-text-muted bg-transparent'"
                  :style="String(form.llm_preset_id) === String(preset.id) ? { background: `linear-gradient(135deg, #6366f1, ${accentColor(activeNav)})` } : {}"
                  @click="form.llm_preset_id = preset.id"
                >
                  {{ preset.name }}
                </button>
                <!-- Link to create -->
                <button
                  v-if="llmPresets.length === 0"
                  class="px-3 py-1.5 rounded-full text-xs font-medium border border-dashed border-border text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors"
                  @click="activeNav = 'llm_presets'"
                >
                  + 创建预设
                </button>
              </div>
              <p v-if="form.llm_preset_id" class="text-[11px] text-text-muted mt-2 flex items-center gap-1">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                使用预设「{{ llmPresets.find(p => p.id === Number(form.llm_preset_id))?.name || '—' }}」中的 URL、Key、Model 等连接参数
              </p>
            </div>

            <!-- Manual config fields (only shown when no preset selected) -->
            <Transition
              enter-active-class="transition duration-200 ease-out"
              enter-from-class="opacity-0 max-h-0"
              enter-to-class="opacity-100 max-h-[500px]"
              leave-active-class="transition duration-150 ease-in"
              leave-from-class="opacity-100 max-h-[500px]"
              leave-to-class="opacity-0 max-h-0"
            >
              <div v-if="!form.llm_preset_id" class="overflow-hidden">
                <!-- LLM Base URL -->
                <div class="mb-4">
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">API URL</label>
                  <input
                    v-model="form.llm_base_url"
                    type="text"
                    placeholder="例如: https://api.openai.com/v1"
                    class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none transition-colors"
                    :style="{ '--tw-ring-color': accentColor(activeNav) }"
                    :class="`focus:border-[${accentColor(activeNav)}]`"
                  />
                </div>
                <!-- LLM API Key -->
                <div class="mb-4">
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">API Key</label>
                  <div class="relative">
                    <input
                      v-model="form.llm_api_key"
                      :type="showApiKey ? 'text' : 'password'"
                      placeholder="sk-..."
                      class="w-full px-3 py-2 pr-10 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none transition-colors font-mono"
                    />
                    <button type="button" class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-secondary" @click="showApiKey = !showApiKey">
                      <svg v-if="showApiKey" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
                      <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" /></svg>
                    </button>
                  </div>
                </div>
                <!-- LLM Model -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">Model</label>
                  <input
                    v-model="form.llm_model"
                    type="text"
                    placeholder="例如: gpt-4o, claude-sonnet-4-20250514, qwen-plus"
                    class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none transition-colors"
                  />
                </div>
              </div>
            </Transition>
          </fieldset>

          <!-- ===== System Prompt Section ===== -->
          <fieldset class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">System Prompt</legend>

            <!-- Prompt preset selector -->
            <div class="mb-4">
              <label class="block text-xs font-medium text-text-secondary mb-2">选择提示词预设</label>
              <div class="flex flex-wrap gap-2">
                <!-- "Use default / custom" pill -->
                <button
                  class="px-3 py-1.5 rounded-full text-xs font-medium border transition-all duration-150"
                  :class="!form.prompt_preset_id
                    ? 'border-transparent text-white shadow-md bg-gradient-to-r from-[#059669] to-[#10b981]'
                    : 'border-border text-text-secondary hover:border-text-muted bg-transparent'"
                  @click="form.prompt_preset_id = ''"
                >
                  自定义
                </button>
                <!-- Prompt preset pills -->
                <button
                  v-for="preset in promptPresets"
                  :key="preset.id"
                  class="px-3 py-1.5 rounded-full text-xs font-medium border transition-all duration-150"
                  :class="String(form.prompt_preset_id) === String(preset.id)
                    ? 'border-transparent text-white shadow-md bg-gradient-to-r from-[#059669] to-[#10b981]'
                    : 'border-border text-text-secondary hover:border-text-muted bg-transparent'"
                  @click="form.prompt_preset_id = preset.id"
                >
                  {{ preset.name }}
                </button>
                <button
                  v-if="promptPresets.length === 0"
                  class="px-3 py-1.5 rounded-full text-xs font-medium border border-dashed border-border text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors"
                  @click="activeNav = 'prompt_presets'"
                >
                  + 创建预设
                </button>
              </div>
              <p v-if="form.prompt_preset_id" class="text-[11px] text-text-muted mt-2 flex items-center gap-1">
                <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" /></svg>
                使用预设「{{ promptPresets.find(p => p.id === Number(form.prompt_preset_id))?.name || '—' }}」作为系统提示词
              </p>
            </div>

            <!-- Custom prompt textarea (only when no preset) -->
            <Transition
              enter-active-class="transition duration-200 ease-out"
              enter-from-class="opacity-0"
              enter-to-class="opacity-100"
              leave-active-class="transition duration-150 ease-in"
              leave-from-class="opacity-100"
              leave-to-class="opacity-0"
            >
              <div v-if="!form.prompt_preset_id">
                <div class="flex items-center justify-between mb-1.5">
                  <label class="text-xs font-medium text-text-secondary">{{ activeNav === 'compare' ? '对比分析系统提示词' : activeNav === 'inspiration' ? '灵感涌现系统提示词' : '灵感生成系统提示词' }}</label>
                  <button
                    v-if="hasDefault('system_prompt')"
                    :disabled="isDefault('system_prompt')"
                    class="shrink-0 px-3 py-1 rounded-lg text-xs border transition-colors"
                    :class="isDefault('system_prompt')
                      ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                      : `border-[${accentColor(activeNav)}]/30 text-[${accentColor(activeNav)}] bg-[${accentColor(activeNav)}]/10 hover:bg-[${accentColor(activeNav)}]/20 cursor-pointer`"
                    :style="!isDefault('system_prompt') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                    @click="resetField('system_prompt')"
                  >恢复默认</button>
                </div>
                <textarea
                  v-model="form.system_prompt"
                  rows="12"
                  class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none transition-colors resize-y leading-relaxed font-mono"
                  placeholder="输入系统提示词..."
                ></textarea>
              </div>
            </Transition>
          </fieldset>

          <!-- ===== Data Source (compare only) ===== -->
          <fieldset v-if="activeNav === 'compare'" class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">数据源配置</legend>
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">对比分析数据源</label>
              <div class="flex items-center gap-2">
                <select
                  v-model="form.data_source"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors appearance-none cursor-pointer"
                >
                  <option value="full_text">全文</option>
                  <option value="abstract">原文摘要</option>
                  <option value="summary">系统总结</option>
                </select>
                <button
                  v-if="hasDefault('data_source')"
                  :disabled="isDefault('data_source')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('data_source')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  @click="resetField('data_source')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ { full_text: '全文', abstract: '原文摘要', summary: '系统总结' }[defaults.data_source] || defaults.data_source }}</p>
              <div class="mt-3 text-[11px] text-text-muted space-y-1">
                <p><span class="text-text-secondary font-medium">全文</span> — 使用 MinerU 从 PDF 提取的完整 Markdown 正文</p>
                <p><span class="text-text-secondary font-medium">原文摘要</span> — 仅使用论文原始摘要，Token 消耗最低</p>
                <p><span class="text-text-secondary font-medium">系统总结</span> — 使用系统生成的中文结构化摘要（默认）</p>
              </div>
            </div>
          </fieldset>

          <!-- Data source info for inspiration -->
          <fieldset v-if="activeNav === 'inspiration'" class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">数据源</legend>
            <div class="flex items-center gap-2 text-sm text-text-secondary">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-[#f59e0b]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              <span>数据源固定为<span class="text-text-primary font-medium">选中的灵感涌现条目内容</span>，无需额外配置。</span>
            </div>
          </fieldset>

          <!-- ===== Generation Parameters (only when using manual config, not preset) ===== -->
          <fieldset v-if="!form.llm_preset_id" class="mb-8 border border-border rounded-xl p-5">
            <legend class="px-2 text-xs font-semibold text-text-secondary">生成参数</legend>

            <!-- Temperature -->
            <div class="mb-5">
              <label class="block text-xs font-medium text-text-secondary mb-1.5">Temperature</label>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="form.temperature"
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors"
                />
                <button
                  v-if="hasDefault('temperature')"
                  :disabled="isDefault('temperature')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('temperature')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  :style="!isDefault('temperature') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                  @click="resetField('temperature')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.temperature }}</p>
            </div>

            <!-- Max Tokens -->
            <div class="mb-5">
              <label class="block text-xs font-medium text-text-secondary mb-1.5">Max Tokens</label>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="form.max_tokens"
                  type="number"
                  step="256"
                  min="256"
                  max="32768"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors"
                />
                <button
                  v-if="hasDefault('max_tokens')"
                  :disabled="isDefault('max_tokens')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('max_tokens')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  :style="!isDefault('max_tokens') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                  @click="resetField('max_tokens')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.max_tokens }}</p>
            </div>

            <!-- Input Hard Limit -->
            <div class="mb-5">
              <label class="block text-xs font-medium text-text-secondary mb-1.5">输入硬上限 (Input Hard Limit)</label>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="form.input_hard_limit"
                  type="number"
                  step="1024"
                  min="1024"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors"
                />
                <button
                  v-if="hasDefault('input_hard_limit')"
                  :disabled="isDefault('input_hard_limit')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('input_hard_limit')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  :style="!isDefault('input_hard_limit') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                  @click="resetField('input_hard_limit')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.input_hard_limit }}</p>
            </div>

            <!-- Input Safety Margin -->
            <div>
              <label class="block text-xs font-medium text-text-secondary mb-1.5">安全边距 (Safety Margin)</label>
              <div class="flex items-center gap-2">
                <input
                  v-model.number="form.input_safety_margin"
                  type="number"
                  step="256"
                  min="0"
                  class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none transition-colors"
                />
                <button
                  v-if="hasDefault('input_safety_margin')"
                  :disabled="isDefault('input_safety_margin')"
                  class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                  :class="isDefault('input_safety_margin')
                    ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                    : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                  :style="!isDefault('input_safety_margin') ? { borderColor: accentColor(activeNav) + '4d', color: accentColor(activeNav), background: accentColor(activeNav) + '1a' } : {}"
                  @click="resetField('input_safety_margin')"
                >恢复默认</button>
              </div>
              <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.input_safety_margin }}</p>
            </div>
          </fieldset>

          <!-- Action buttons -->
          <div class="flex items-center justify-between pb-8">
            <div class="text-xs">
              <Transition
                enter-active-class="transition duration-200 ease-out"
                enter-from-class="opacity-0"
                enter-to-class="opacity-100"
                leave-active-class="transition duration-150 ease-in"
                leave-from-class="opacity-100"
                leave-to-class="opacity-0"
              >
                <span v-if="saveSuccess" class="text-tinder-green flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  保存成功
                </span>
                <span v-else-if="saveError" class="text-tinder-pink">{{ saveError }}</span>
              </Transition>
            </div>
            <button
              class="px-6 py-2.5 rounded-lg text-sm font-semibold border-none cursor-pointer transition-all"
              :class="saving
                ? 'opacity-50 cursor-not-allowed'
                : 'text-white hover:opacity-90 shadow-lg'"
              :style="{
                background: saving ? accentColor(activeNav) + '80' : `linear-gradient(135deg, #6366f1, ${accentColor(activeNav)})`,
                boxShadow: saving ? 'none' : `0 10px 25px ${accentColor(activeNav)}33`,
              }"
              :disabled="saving"
              @click="handleSave"
            >
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </template>
      </div>

      <!-- ============================== -->
      <!-- Idea Generate Config page -->
      <!-- ============================== -->
      <div v-else-if="activeNav === 'idea_generate'" class="max-w-3xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center h-full min-h-[400px]">
          <div class="text-center">
            <div class="relative w-12 h-12 mx-auto mb-3 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#f97316] border-r-[#fb923c] animate-spin"></div>
            </div>
            <p class="text-sm text-text-muted">加载设置...</p>
          </div>
        </div>

        <template v-else>
          <!-- Section title -->
          <div class="mb-6">
            <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#f97316]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M9 18h6" /><path d="M10 22h4" /><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
              </svg>
              灵感生成配置
            </h2>
            <p class="text-xs text-text-muted mt-1">
              为各处理阶段配置大语言模型与提示词预设，未配置时使用系统默认值。
            </p>
          </div>

          <!-- ===== 全局 LLM 兜底配置 ===== -->
          <div class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">🌐</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">全局默认模型</h3>
                <p class="text-[11px] text-text-muted">当某阶段未单独配置模型时使用此预设；也可手动填写 URL/Key/Model</p>
              </div>
            </div>
            <div class="px-5 py-4">
              <!-- Global LLM preset selector -->
              <div class="mb-3">
                <label class="block text-xs font-medium text-text-secondary mb-2">选择全局模型预设</label>
                <div class="flex flex-wrap gap-1.5">
                  <button
                    class="px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150"
                    :class="!form.llm_preset_id
                      ? 'border-transparent text-white shadow-sm'
                      : 'border-border text-text-secondary hover:border-[#f97316]/50 bg-transparent'"
                    :style="!form.llm_preset_id ? { background: 'linear-gradient(135deg, #ea580c, #f97316)' } : {}"
                    @click="form.llm_preset_id = ''"
                  >手动配置</button>
                  <button
                    v-for="preset in llmPresets"
                    :key="preset.id"
                    class="px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150"
                    :class="String(form.llm_preset_id) === String(preset.id)
                      ? 'border-transparent text-white shadow-sm'
                      : 'border-border text-text-secondary hover:border-[#f97316]/50 bg-transparent'"
                    :style="String(form.llm_preset_id) === String(preset.id) ? { background: 'linear-gradient(135deg, #ea580c, #f97316)' } : {}"
                    @click="form.llm_preset_id = preset.id"
                  >{{ preset.name }}</button>
                  <button
                    v-if="llmPresets.length === 0"
                    class="px-2.5 py-1 rounded-full text-xs border border-dashed border-border text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors"
                    @click="activeNav = 'llm_presets'"
                  >+ 创建预设</button>
                </div>
              </div>
              <!-- Manual config (when no preset) -->
              <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0 max-h-0" enter-to-class="opacity-100 max-h-[300px]" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100 max-h-[300px]" leave-to-class="opacity-0 max-h-0">
                <div v-if="!form.llm_preset_id" class="overflow-hidden mt-3 space-y-3">
                  <div>
                    <label class="block text-xs font-medium text-text-secondary mb-1">API URL</label>
                    <input v-model="form.llm_base_url" type="text" placeholder="https://api.openai.com/v1" class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#f97316] transition-colors" />
                  </div>
                  <div>
                    <label class="block text-xs font-medium text-text-secondary mb-1">API Key</label>
                    <input v-model="form.llm_api_key" type="password" placeholder="sk-..." class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm font-mono focus:outline-none focus:border-[#f97316] transition-colors" />
                  </div>
                  <div>
                    <label class="block text-xs font-medium text-text-secondary mb-1">Model</label>
                    <input v-model="form.llm_model" type="text" placeholder="例如: gpt-4o, claude-sonnet-4" class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm focus:outline-none focus:border-[#f97316] transition-colors" />
                  </div>
                </div>
              </Transition>
            </div>
          </div>

          <!-- ===== 阶段模块配置卡片 ===== -->
          <div v-for="mod in ideaModules" :key="mod.key" class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <!-- Module header -->
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">{{ mod.icon }}</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h3>
                <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
              </div>
            </div>

            <div class="divide-y divide-border/50">
              <!-- LLM preset row (only show module-specific rows, not the global "plan" row that uses llm_preset_id) -->
              <div v-if="mod.llmFormKey !== 'llm_preset_id'" class="px-5 py-3.5 flex items-start gap-3">
                <div class="w-36 shrink-0 flex items-center gap-1.5 pt-1">
                  <span class="text-sm">🤖</span>
                  <span class="text-xs font-medium text-text-secondary">专用模型预设</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex flex-wrap gap-1.5">
                    <button
                      v-for="preset in llmPresets"
                      :key="preset.id"
                      class="px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150"
                      :class="String(form[mod.llmFormKey]) === String(preset.id)
                        ? 'border-transparent text-white shadow-sm'
                        : 'border-border text-text-secondary hover:border-[#f97316]/50 bg-transparent'"
                      :style="String(form[mod.llmFormKey]) === String(preset.id) ? { background: 'linear-gradient(135deg, #ea580c, #f97316)' } : {}"
                      @click="form[mod.llmFormKey] = preset.id"
                    >{{ preset.name }}</button>
                    <button
                      v-if="llmPresets.length === 0"
                      class="px-2.5 py-1 rounded-full text-xs border border-dashed border-border text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors"
                      @click="activeNav = 'llm_presets'"
                    >+ 创建预设</button>
                    <button
                      v-if="form[mod.llmFormKey]"
                      class="px-2 py-1 rounded-full text-[11px] border border-border/60 text-text-muted hover:text-red-400 hover:border-red-400/40 transition-colors leading-none"
                      @click="form[mod.llmFormKey] = null"
                    >✕</button>
                  </div>
                  <p v-if="form[mod.llmFormKey]" class="text-[11px] text-text-muted mt-1.5 flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-green-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
                    已选：{{ llmPresets.find(p => p.id === Number(form[mod.llmFormKey]))?.name || '—' }}
                  </p>
                  <p v-else-if="llmPresets.length > 0" class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用全局默认配置</p>
                </div>
              </div>

              <!-- Prompt preset rows -->
              <div v-for="prompt in mod.prompts" :key="prompt.formKey" class="px-5 py-3.5 flex items-start gap-3">
                <div class="w-36 shrink-0 flex items-center gap-1.5 pt-1">
                  <span class="text-sm">📝</span>
                  <span class="text-xs font-medium text-text-secondary">{{ prompt.label }}</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex flex-wrap gap-1.5">
                    <button
                      v-for="preset in promptPresets"
                      :key="preset.id"
                      class="px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150"
                      :class="String(form[prompt.formKey]) === String(preset.id)
                        ? 'border-transparent text-white shadow-sm bg-gradient-to-r from-[#ea580c] to-[#f97316]'
                        : 'border-border text-text-secondary hover:border-[#f97316]/50 bg-transparent'"
                      @click="form[prompt.formKey] = preset.id"
                    >{{ preset.name }}</button>
                    <button
                      v-if="promptPresets.length === 0"
                      class="px-2.5 py-1 rounded-full text-xs border border-dashed border-border text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors"
                      @click="activeNav = 'prompt_presets'"
                    >+ 创建预设</button>
                    <button
                      v-if="form[prompt.formKey]"
                      class="px-2 py-1 rounded-full text-[11px] border border-border/60 text-text-muted hover:text-red-400 hover:border-red-400/40 transition-colors leading-none"
                      @click="form[prompt.formKey] = null"
                    >✕</button>
                  </div>
                  <p v-if="form[prompt.formKey]" class="text-[11px] text-text-muted mt-1.5 flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-emerald-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
                    已选：{{ promptPresets.find(p => p.id === Number(form[prompt.formKey]))?.name || '—' }}
                  </p>
                  <p v-else-if="promptPresets.length > 0" class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用系统默认提示词</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Action buttons -->
          <div class="flex items-center justify-between pb-8 mt-4">
            <div class="text-xs">
              <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="opacity-0" enter-to-class="opacity-100" leave-active-class="transition duration-150 ease-in" leave-from-class="opacity-100" leave-to-class="opacity-0">
                <span v-if="saveSuccess" class="text-tinder-green flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  保存成功
                </span>
                <span v-else-if="saveError" class="text-tinder-pink">{{ saveError }}</span>
              </Transition>
            </div>
            <button
              class="px-6 py-2.5 rounded-lg text-sm font-semibold border-none cursor-pointer transition-all"
              :class="saving ? 'opacity-50 cursor-not-allowed' : 'text-white hover:opacity-90 shadow-lg'"
              :style="{
                background: saving ? '#f9731680' : 'linear-gradient(135deg, #ea580c, #f97316)',
                boxShadow: saving ? 'none' : '0 10px 25px #f9731633',
              }"
              :disabled="saving"
              @click="handleSave"
            >
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </template>
      </div>

      <!-- ============================== -->
      <!-- Paper Recommend Config page -->
      <!-- ============================== -->
      <div v-else-if="activeNav === 'paper_recommend'" class="max-w-3xl mx-auto px-4 sm:px-8 py-6 sm:py-8">
        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center h-full min-h-[400px]">
          <div class="text-center">
            <div class="relative w-12 h-12 mx-auto mb-3 flex items-center justify-center">
              <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#ec4899] border-r-[#f472b6] animate-spin"></div>
            </div>
            <p class="text-sm text-text-muted">加载设置...</p>
          </div>
        </div>

        <template v-else>
          <!-- Section title -->
          <div class="mb-6">
            <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#ec4899]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
              </svg>
              推荐论文参数配置
            </h2>
            <p class="text-xs text-text-muted mt-1">
              为各处理阶段配置大语言模型与提示词预设，未配置时使用系统默认值。
            </p>
          </div>

          <!-- ===== MinerU Token ===== -->
          <div class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">🔑</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">MinerU Token</h3>
                <p class="text-[11px] text-text-muted">用于 PDF 解析的 MinerU 服务凭证；留空则使用系统默认配置</p>
              </div>
            </div>
            <div class="px-5 py-4 flex items-center gap-2">
              <div class="relative flex-1">
                <input
                  v-model="form.mineru_token"
                  :type="mineruTokenVisible ? 'text' : 'password'"
                  placeholder="留空使用系统配置"
                  class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors pr-10 font-mono"
                />
                <button
                  class="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors text-xs select-none"
                  @click="mineruTokenVisible = !mineruTokenVisible"
                >{{ mineruTokenVisible ? '🙈' : '👁' }}</button>
              </div>
            </div>
          </div>

          <!-- ===== 功能模块配置卡片 ===== -->
          <div v-for="mod in recommendModules" :key="mod.key" class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <!-- Module header — matches admin style -->
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">{{ mod.icon }}</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h3>
                <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
              </div>
            </div>

            <div class="divide-y divide-border/50">
              <!-- LLM preset row -->
              <div class="px-5 py-3.5 flex items-start gap-3">
                <div class="w-32 shrink-0 flex items-center gap-1.5 pt-1">
                  <span class="text-sm">🤖</span>
                  <span class="text-xs font-medium text-text-secondary">调用模型预设</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex flex-wrap gap-1.5">
                    <button
                      v-for="preset in llmPresets"
                      :key="preset.id"
                      class="px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150"
                      :class="String(form[mod.llmFormKey]) === String(preset.id)
                        ? 'border-transparent text-white shadow-sm'
                        : 'border-border text-text-secondary hover:border-[#ec4899]/50 bg-transparent'"
                      :style="String(form[mod.llmFormKey]) === String(preset.id) ? { background: 'linear-gradient(135deg, #db2777, #ec4899)' } : {}"
                      @click="form[mod.llmFormKey] = preset.id"
                    >{{ preset.name }}</button>
                    <button
                      v-if="llmPresets.length === 0"
                      class="px-2.5 py-1 rounded-full text-xs border border-dashed border-border text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors"
                      @click="activeNav = 'llm_presets'"
                    >+ 创建预设</button>
                    <button
                      v-if="form[mod.llmFormKey]"
                      class="px-2 py-1 rounded-full text-[11px] border border-border/60 text-text-muted hover:text-red-400 hover:border-red-400/40 transition-colors leading-none"
                      @click="form[mod.llmFormKey] = null"
                    >✕</button>
                  </div>
                  <p v-if="form[mod.llmFormKey]" class="text-[11px] text-text-muted mt-1.5 flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-green-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
                    已选：{{ llmPresets.find(p => p.id === Number(form[mod.llmFormKey]))?.name || '—' }}
                  </p>
                  <p v-else-if="llmPresets.length > 0" class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用系统默认配置</p>
                </div>
              </div>

              <!-- Prompt preset rows -->
              <div v-for="prompt in mod.prompts" :key="prompt.formKey" class="px-5 py-3.5 flex items-start gap-3">
                <div class="w-32 shrink-0 flex items-center gap-1.5 pt-1">
                  <span class="text-sm">📝</span>
                  <span class="text-xs font-medium text-text-secondary">{{ prompt.label }}</span>
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex flex-wrap gap-1.5">
                    <button
                      v-for="preset in promptPresets"
                      :key="preset.id"
                      class="px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150"
                      :class="String(form[prompt.formKey]) === String(preset.id)
                        ? 'border-transparent text-white shadow-sm bg-gradient-to-r from-[#059669] to-[#10b981]'
                        : 'border-border text-text-secondary hover:border-[#10b981]/50 bg-transparent'"
                      @click="form[prompt.formKey] = preset.id"
                    >{{ preset.name }}</button>
                    <button
                      v-if="promptPresets.length === 0"
                      class="px-2.5 py-1 rounded-full text-xs border border-dashed border-border text-text-muted hover:text-text-secondary hover:border-text-muted transition-colors"
                      @click="activeNav = 'prompt_presets'"
                    >+ 创建预设</button>
                    <button
                      v-if="form[prompt.formKey]"
                      class="px-2 py-1 rounded-full text-[11px] border border-border/60 text-text-muted hover:text-red-400 hover:border-red-400/40 transition-colors leading-none"
                      @click="form[prompt.formKey] = null"
                    >✕</button>
                  </div>
                  <p v-if="form[prompt.formKey]" class="text-[11px] text-text-muted mt-1.5 flex items-center gap-1">
                    <svg xmlns="http://www.w3.org/2000/svg" class="w-3 h-3 text-emerald-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6 9 17l-5-5" /></svg>
                    已选：{{ promptPresets.find(p => p.id === Number(form[prompt.formKey]))?.name || '—' }}
                  </p>
                  <p v-else-if="promptPresets.length > 0" class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用系统默认配置</p>
                </div>
              </div>
            </div>
          </div>

          <!-- ===== 字数上限配置 ===== -->
          <div class="mb-4 rounded-xl bg-bg-card border border-border overflow-hidden">
            <div class="px-5 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-3">
              <span class="text-base leading-none">📏</span>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold text-text-primary">字数上限配置</h3>
                <p class="text-[11px] text-text-muted">控制摘要各部分的字数上限（按去空白字符计），超出则调用模型压缩</p>
              </div>
            </div>

            <div class="p-5">
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <!-- section_limit_intro -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">文章简介</label>
                  <div class="flex items-center gap-2">
                    <input
                      v-model.number="form.section_limit_intro"
                      type="number" step="10" min="50" max="1000"
                      class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                    />
                    <button
                      v-if="hasDefault('section_limit_intro')"
                      :disabled="isDefault('section_limit_intro')"
                      class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                      :class="isDefault('section_limit_intro') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                      @click="resetField('section_limit_intro')"
                    >重置</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaults.section_limit_intro }}</p>
                </div>

                <!-- section_limit_method -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">重点思路</label>
                  <div class="flex items-center gap-2">
                    <input
                      v-model.number="form.section_limit_method"
                      type="number" step="10" min="50" max="1000"
                      class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                    />
                    <button
                      v-if="hasDefault('section_limit_method')"
                      :disabled="isDefault('section_limit_method')"
                      class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                      :class="isDefault('section_limit_method') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                      @click="resetField('section_limit_method')"
                    >重置</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaults.section_limit_method }}</p>
                </div>

                <!-- section_limit_findings -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">分析总结</label>
                  <div class="flex items-center gap-2">
                    <input
                      v-model.number="form.section_limit_findings"
                      type="number" step="10" min="50" max="1000"
                      class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                    />
                    <button
                      v-if="hasDefault('section_limit_findings')"
                      :disabled="isDefault('section_limit_findings')"
                      class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                      :class="isDefault('section_limit_findings') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                      @click="resetField('section_limit_findings')"
                    >重置</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaults.section_limit_findings }}</p>
                </div>

                <!-- section_limit_opinion -->
                <div>
                  <label class="block text-xs font-medium text-text-secondary mb-1.5">个人观点</label>
                  <div class="flex items-center gap-2">
                    <input
                      v-model.number="form.section_limit_opinion"
                      type="number" step="10" min="50" max="1000"
                      class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                    />
                    <button
                      v-if="hasDefault('section_limit_opinion')"
                      :disabled="isDefault('section_limit_opinion')"
                      class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                      :class="isDefault('section_limit_opinion') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                      @click="resetField('section_limit_opinion')"
                    >重置</button>
                  </div>
                  <p class="text-[10px] text-text-muted mt-0.5">默认: {{ defaults.section_limit_opinion }}</p>
                </div>
              </div>

              <!-- headline_limit -->
              <div class="mt-4 pt-4 border-t border-border/50">
                <label class="block text-xs font-medium text-text-secondary mb-1.5">首行字数上限</label>
                <div class="flex items-center gap-2">
                  <input
                    v-model.number="form.headline_limit"
                    type="number" step="1" min="10" max="50"
                    class="w-40 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#ec4899] transition-colors"
                  />
                  <button
                    v-if="hasDefault('headline_limit')"
                    :disabled="isDefault('headline_limit')"
                    class="shrink-0 px-2 py-1.5 rounded-lg text-[11px] border transition-colors"
                    :class="isDefault('headline_limit') ? 'border-border text-text-muted bg-transparent cursor-not-allowed' : 'border-[#ec4899]/30 text-[#ec4899] bg-[#ec4899]/10 hover:bg-[#ec4899]/20 cursor-pointer'"
                    @click="resetField('headline_limit')"
                  >重置</button>
                  <span class="text-[11px] text-text-muted">默认: {{ defaults.headline_limit }}</span>
                </div>
                <p class="text-[10px] text-text-muted mt-1">「机构：一句话概括」的首行长度上限</p>
              </div>
            </div>
          </div>

          <!-- Action buttons -->
          <div class="flex items-center justify-between pb-8">
            <div class="text-xs">
              <Transition
                enter-active-class="transition duration-200 ease-out"
                enter-from-class="opacity-0"
                enter-to-class="opacity-100"
                leave-active-class="transition duration-150 ease-in"
                leave-from-class="opacity-100"
                leave-to-class="opacity-0"
              >
                <span v-if="saveSuccess" class="text-tinder-green flex items-center gap-1">
                  <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                  保存成功
                </span>
                <span v-else-if="saveError" class="text-tinder-pink">{{ saveError }}</span>
              </Transition>
            </div>
            <button
              class="px-6 py-2.5 rounded-lg text-sm font-semibold border-none cursor-pointer transition-all"
              :class="saving
                ? 'opacity-50 cursor-not-allowed'
                : 'text-white hover:opacity-90 shadow-lg'"
              :style="{
                background: saving ? '#ec489980' : 'linear-gradient(135deg, #db2777, #ec4899)',
                boxShadow: saving ? 'none' : '0 10px 25px #ec489933',
              }"
              :disabled="saving"
              @click="handleSave"
            >
              {{ saving ? '保存中...' : '保存设置' }}
            </button>
          </div>
        </template>
      </div>

      <!-- ============================== -->
      <!-- Placeholder for disabled features -->
      <!-- ============================== -->
      <div v-else class="flex items-center justify-center h-full">
        <div class="text-center">
          <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-bg-elevated flex items-center justify-center">
            <span class="text-3xl opacity-30">
              <span v-if="activeNav === 'paper_summary'">📄</span>
              <span v-else-if="activeNav === 'theme_filter'">🔍</span>
              <span v-else>⚙️</span>
            </span>
          </div>
          <h3 class="text-sm font-semibold text-text-muted mb-1">{{ navItems.find(i => i.key === activeNav)?.label }}</h3>
          <p class="text-xs text-text-muted">此功能即将推出，敬请期待</p>
        </div>
      </div>
    </div>
  </div>
</template>
