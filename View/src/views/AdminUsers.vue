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
  resetSystemConfig,
} from '../api'
import type { AuthUser, UserTier, UserRole, PipelineRunStatus, ScheduleConfig, SystemConfigResponse, SystemConfigGroup, SystemConfigItem } from '../types/paper'
import { isSuperAdmin, currentUser } from '../stores/auth'

// ---------------------------------------------------------------------------
// Sidebar menu state
// ---------------------------------------------------------------------------
const activeTab = ref<'users' | 'roles' | 'pipeline' | 'schedule' | 'config'>('users')

const menuItems = computed(() => {
  const items: { key: 'users' | 'roles' | 'pipeline' | 'schedule' | 'config'; icon: string; label: string; desc: string; group?: string }[] = [
    { key: 'users', icon: '👥', label: '用户等级', desc: '管理用户访问等级', group: '用户' },
  ]
  if (isSuperAdmin.value) {
    items.push({ key: 'roles', icon: '🛡️', label: '权限管理', desc: '管理用户角色权限', group: '用户' })
  }
  items.push(
    { key: 'pipeline', icon: '🚀', label: '脚本执行', desc: '手动运行 Pipeline', group: '运维' },
    { key: 'schedule', icon: '🕐', label: '定时调度', desc: '自动定时执行配置', group: '运维' },
    { key: 'config', icon: '⚙️', label: '系统配置', desc: '管理系统配置项', group: '系统' },
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
const configDefaults = ref<Record<string, any>>({})
const configLoading = ref(false)
const configSaving = ref(false)
const configError = ref('')
const configValues = ref<Record<string, any>>({})
const expandedGroups = ref<Set<string>>(new Set())

// 大模型配置的子分组定义
const llmSubGroups = {
  '主题相关性评分模型': ['theme_select_base_url', 'theme_select_model', 'theme_select_max_tokens', 'theme_select_temperature', 'theme_select_concurrency'],
  '机构判别模型': ['org_base_url', 'org_model', 'org_max_tokens', 'org_temperature', 'pdf_info_concurrency'],
  '摘要生成模型 (Qwen)': ['summary_base_url', 'summary_model', 'summary_max_tokens', 'summary_temperature', 'summary_input_hard_limit', 'summary_input_safety_margin', 'summary_concurrency'],
  '摘要生成模型2 (GPTGod Claude)': ['summary_base_url_2', 'summary_gptgod_apikey', 'summary_model_2'],
  '摘要生成模型3 (VectorEngine Claude)': ['summary_base_url_3', 'summary_apikey_3', 'summary_model_3'],
  '摘要精简模型 (Qwen)': ['summary_limit_base_url', 'summary_limit_model', 'summary_limit_max_tokens', 'summary_limit_temperature', 'summary_limit_concurrency', 'summary_limit_input_hard_limit', 'summary_limit_input_safety_margin'],
  '摘要精简模型2 (GPTGod Claude)': ['summary_limit_url_2', 'summary_limit_gptgod_apikey', 'summary_limit_model_2'],
  '摘要精简模型3 (VectorEngine Claude)': ['summary_limit_url_3', 'summary_limit_apikey_3', 'summary_limit_model_3'],
  '批量摘要配置': ['summary_batch_base_url', 'summary_batch_api_key', 'summary_batch_model', 'summary_batch_temperature', 'summary_batch_completion_window', 'summary_batch_endpoint'],
  'API Keys': ['minerU_Token', 'qwen_api_key', 'nvidia_api_key'],
  '其他': ['SLLM'],
}

// 提示词配置的子分组定义
const promptSubGroups = {
  '主题相关性评分提示词': ['theme_select_system_prompt'],
  '摘要生成提示词': ['system_prompt', 'summary_example'],
  '摘要精简提示词': ['summary_limit_prompt_intro', 'summary_limit_prompt_method', 'summary_limit_prompt_findings', 'summary_limit_prompt_opinion', 'summary_limit_prompt_structure_check', 'summary_limit_prompt_structure_rewrite', 'summary_limit_prompt_headline'],
  '批量摘要提示词': ['summary_batch_system_prompt'],
  '机构判断提示词': ['pdf_info_system_prompt'],
  '论文结构化抽取提示词': ['paper_assets_system_prompt'],
}

function toggleGroup(groupName: string) {
  if (expandedGroups.value.has(groupName)) {
    expandedGroups.value.delete(groupName)
  } else {
    expandedGroups.value.add(groupName)
  }
}

function isGroupExpanded(groupName: string): boolean {
  return expandedGroups.value.has(groupName)
}

function getSubGroupItems(groupName: string, subGroupName: string, items: SystemConfigItem[]): SystemConfigItem[] {
  const keys = groupName === '大模型调用配置' ? llmSubGroups[subGroupName as keyof typeof llmSubGroups] : promptSubGroups[subGroupName as keyof typeof promptSubGroups]
  if (!keys) return []
  return items.filter(item => keys.includes(item.key))
}

async function loadSystemConfig() {
  configLoading.value = true
  configError.value = ''
  try {
    const res = await getSystemConfig()
    configGroups.value = res.groups
    configDefaults.value = res.defaults
    // 初始化配置值
    const values: Record<string, any> = {}
    for (const group of res.groups) {
      for (const item of group.items) {
        values[item.key] = item.value
      }
    }
    configValues.value = values
    // 默认展开所有分组
    expandedGroups.value = new Set(res.groups.map(g => g.name))
  } catch (e: any) {
    configError.value = e?.response?.data?.detail || '加载配置失败'
  } finally {
    configLoading.value = false
  }
}

async function handleSaveConfig() {
  configSaving.value = true
  configError.value = ''
  try {
    await updateSystemConfig(configValues.value)
    await loadSystemConfig()
    window.alert('配置已保存')
  } catch (e: any) {
    configError.value = e?.response?.data?.detail || '保存配置失败'
    window.alert(configError.value)
  } finally {
    configSaving.value = false
  }
}

async function handleResetConfig() {
  if (!confirm('确定要重置所有配置为默认值吗？此操作不可撤销。')) return
  try {
    await resetSystemConfig()
    await loadSystemConfig()
    window.alert('配置已重置为默认值')
  } catch (e: any) {
    configError.value = e?.response?.data?.detail || '重置配置失败'
    window.alert(configError.value)
  }
}

function maskSensitiveValue(value: any, isSensitive: boolean): string {
  if (!isSensitive) return String(value)
  const str = String(value)
  if (str.length <= 8) return '****'
  return str.substring(0, 4) + '****' + str.substring(str.length - 4)
}

function getInputType(item: SystemConfigItem): string {
  if (item.type === 'bool' || item.type === 'bool') return 'checkbox'
  if (item.type === 'int' || item.type === 'float') return 'number'
  if (item.type === 'list') return 'textarea'
  return 'text'
}

function formatValueForInput(item: SystemConfigItem, value: any): string {
  if (item.type === 'list' && Array.isArray(value)) {
    return JSON.stringify(value, null, 2)
  }
  if (item.type === 'bool') {
    return value ? 'true' : 'false'
  }
  return String(value ?? '')
}

function parseValueFromInput(item: SystemConfigItem, inputValue: string): any {
  if (item.type === 'list') {
    try {
      return JSON.parse(inputValue)
    } catch {
      // 尝试逗号分隔
      return inputValue.split(',').map(s => s.trim()).filter(s => s)
    }
  }
  if (item.type === 'bool') {
    return inputValue === 'true' || inputValue === '1' || inputValue === 'on'
  }
  if (item.type === 'int') {
    return parseInt(inputValue, 10)
  }
  if (item.type === 'float') {
    return parseFloat(inputValue)
  }
  return inputValue
}

// Watch activeTab to load config when switching to config tab
watch(activeTab, (newTab) => {
  if (newTab === 'config' && configGroups.value.length === 0) {
    loadSystemConfig()
  }
})

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

          <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
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
      <!-- Page: System Config -->
      <!-- ============================================================= -->
      <div v-if="activeTab === 'config'" class="flex-1 flex flex-col p-6 gap-4 overflow-auto">
        <div class="shrink-0 flex items-center justify-between">
          <div>
            <h1 class="text-lg font-bold text-text-primary">⚙️ 系统配置</h1>
            <p class="text-xs text-text-muted mt-0.5">管理系统配置项，修改将保存到配置文件</p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1.5 rounded-full border border-border text-xs text-text-secondary bg-transparent cursor-pointer hover:bg-bg-hover transition-colors"
              @click="loadSystemConfig"
            >
              🔄 刷新
            </button>
            <button
              :disabled="configSaving"
              class="px-5 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-white text-sm font-medium shadow-lg shadow-green-600/20 transition-all duration-200 disabled:opacity-50"
              @click="handleSaveConfig"
            >
              {{ configSaving ? '保存中...' : '💾 保存配置' }}
            </button>
            <button
              class="px-5 py-2 rounded-lg bg-red-600/20 text-red-400 border border-red-500/30 text-sm font-medium hover:bg-red-600/30 transition-all duration-200"
              @click="handleResetConfig"
            >
              🔄 重置为默认值
            </button>
          </div>
        </div>

        <div v-if="configLoading" class="flex-1 flex items-center justify-center text-text-muted">
          <div class="flex items-center gap-2">
            <span class="inline-block w-4 h-4 border-2 border-text-muted border-t-transparent rounded-full animate-spin"></span>
            加载中...
          </div>
        </div>
        <div v-else-if="configError" class="flex-1 flex items-center justify-center text-red-400">{{ configError }}</div>
        <div v-else class="flex-1 overflow-auto space-y-4">
          <div v-for="group in configGroups" :key="group.name" class="rounded-xl bg-bg-card border border-border overflow-hidden">
            <!-- Group Header (Collapsible) -->
            <button
              class="w-full px-5 py-4 flex items-center justify-between hover:bg-bg-hover transition-colors"
              @click="toggleGroup(group.name)"
            >
              <h2 class="text-sm font-semibold text-text-primary">{{ group.name }}</h2>
              <span class="text-text-muted text-lg transition-transform" :class="isGroupExpanded(group.name) ? 'rotate-90' : ''">
                ▶
              </span>
            </button>
            
            <!-- Group Content (Collapsible) -->
            <div v-show="isGroupExpanded(group.name)" class="px-5 pb-5 space-y-4">
              
              <!-- 大模型配置和提示词配置使用表格模式 -->
              <template v-if="group.name === '大模型调用配置' || group.name === '提示词配置'">
                <div v-for="(subGroupKeys, subGroupName) in (group.name === '大模型调用配置' ? llmSubGroups : promptSubGroups)" :key="subGroupName" class="mb-6">
                  <h3 class="text-xs font-medium text-text-secondary mb-3">{{ subGroupName }}</h3>
                  
                  <!-- 配置表格 -->
                  <div class="rounded-lg bg-bg-elevated border border-border overflow-hidden mb-3">
                    <div class="overflow-x-auto">
                      <table class="w-full text-sm min-w-full">
                        <thead class="bg-bg-sidebar border-b border-border">
                          <tr>
                            <th class="text-left px-4 py-2 font-medium text-text-muted text-xs w-12 sticky left-0 bg-bg-sidebar z-10">
                              <input type="checkbox" class="cursor-pointer" />
                            </th>
                            <th v-for="item in getSubGroupItems(group.name, subGroupName, group.items)" :key="item.key" class="text-left px-4 py-2 font-medium text-text-muted text-xs whitespace-nowrap min-w-[150px]">
                              {{ item.key }}
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr class="border-b border-border/50 hover:bg-bg-hover/30 transition-colors">
                            <td class="px-4 py-3 sticky left-0 bg-bg-elevated z-10">
                              <input type="checkbox" class="cursor-pointer" />
                            </td>
                            <td v-for="item in getSubGroupItems(group.name, subGroupName, group.items)" :key="item.key" class="px-4 py-3 text-text-primary text-xs whitespace-nowrap">
                              <span v-if="item.is_sensitive" class="font-mono">{{ maskSensitiveValue(configValues[item.key], true) }}</span>
                              <span v-else class="truncate max-w-[200px] block" :title="String(configValues[item.key] ?? '')">
                                {{ String(configValues[item.key] ?? '').substring(0, 50) }}{{ String(configValues[item.key] ?? '').length > 50 ? '...' : '' }}
                              </span>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                  
                  <!-- 编辑表单 -->
                  <div class="rounded-lg bg-bg-elevated border border-border p-4 space-y-3">
                    <div v-for="item in getSubGroupItems(group.name, subGroupName, group.items)" :key="item.key" class="flex flex-col gap-2">
                      <label class="block text-xs font-medium text-text-primary">
                        {{ item.key }}
                        <span v-if="item.is_sensitive" class="ml-1 text-[10px] text-amber-400">(敏感信息)</span>
                        <span v-if="item.description" class="ml-2 text-[10px] text-text-muted font-normal">- {{ item.description }}</span>
                      </label>
                      
                      <!-- 布尔值 -->
                      <div v-if="item.type === 'bool'" class="flex items-center gap-2">
                        <label class="relative inline-flex items-center cursor-pointer">
                          <input
                            type="checkbox"
                            class="sr-only peer"
                            :checked="configValues[item.key] === true"
                            @change="configValues[item.key] = ($event.target as HTMLInputElement).checked"
                          />
                          <div class="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                        </label>
                        <span class="text-sm text-text-secondary">{{ configValues[item.key] ? '开启' : '关闭' }}</span>
                      </div>
                      
                      <!-- 数字 -->
                      <input
                        v-else-if="item.type === 'int' || item.type === 'float'"
                        :value="String(configValues[item.key] ?? '')"
                        :type="'number'"
                        :step="item.type === 'float' ? '0.1' : undefined"
                        class="w-full px-3 py-2 rounded-lg bg-bg border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                        @input="(e) => { const val = (e.target as HTMLInputElement).value; if (item.type === 'int') configValues[item.key] = parseInt(val, 10) || 0; else if (item.type === 'float') configValues[item.key] = parseFloat(val) || 0; }"
                      />
                      
                      <!-- 长字符串使用 textarea -->
                      <textarea
                        v-else-if="item.type === 'str' && (typeof configValues[item.key] === 'string' && configValues[item.key].length > 100)"
                        :value="String(configValues[item.key] ?? '')"
                        class="w-full px-3 py-2 rounded-lg bg-bg border border-border text-text-primary text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500/50 resize-y min-h-[100px]"
                        @input="configValues[item.key] = ($event.target as HTMLTextAreaElement).value"
                      />
                      
                      <!-- 普通字符串 -->
                      <input
                        v-else
                        :value="String(configValues[item.key] ?? '')"
                        type="text"
                        class="w-full px-3 py-2 rounded-lg bg-bg border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                        :class="item.is_sensitive ? 'font-mono' : ''"
                        @input="configValues[item.key] = ($event.target as HTMLInputElement).value"
                      />
                    </div>
                  </div>
                </div>
              </template>
              
              <!-- 其他配置使用原来的方式 -->
              <template v-else>
                <div class="space-y-4">
                  <div v-for="item in group.items" :key="item.key" class="flex flex-col gap-2">
                <div class="flex items-start justify-between gap-4">
                  <div class="flex-1 min-w-0">
                    <label class="block text-xs font-medium text-text-primary mb-1">
                      {{ item.key }}
                      <span v-if="item.is_sensitive" class="ml-1 text-[10px] text-amber-400">(敏感信息)</span>
                    </label>
                    <p v-if="item.description" class="text-[11px] text-text-muted mb-2">{{ item.description }}</p>
                  </div>
                  <div class="text-xs text-text-muted font-mono bg-bg-elevated px-2 py-1 rounded">
                    {{ item.type }}
                  </div>
                </div>
                
                <!-- 布尔值使用 checkbox -->
                <div v-if="item.type === 'bool'" class="flex items-center gap-2">
                  <label class="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      class="sr-only peer"
                      :checked="configValues[item.key] === true"
                      @change="configValues[item.key] = ($event.target as HTMLInputElement).checked"
                    />
                    <div class="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                  </label>
                  <span class="text-sm text-text-secondary">{{ configValues[item.key] ? '开启' : '关闭' }}</span>
                </div>
                
                <!-- 数组使用 textarea -->
                <textarea
                  v-else-if="item.type === 'list'"
                  :value="Array.isArray(configValues[item.key]) ? JSON.stringify(configValues[item.key], null, 2) : String(configValues[item.key] ?? '')"
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500/50 resize-y min-h-[80px]"
                  placeholder='输入 JSON 数组或逗号分隔的值&#10;例如: ["value1", "value2"] 或 value1, value2'
                  @input="(e) => { try { configValues[item.key] = JSON.parse((e.target as HTMLTextAreaElement).value); } catch { const val = (e.target as HTMLTextAreaElement).value; configValues[item.key] = val.split(',').map(s => s.trim()).filter(s => s); } }"
                />
                
                <!-- 字符串使用 textarea（如果很长） -->
                <textarea
                  v-else-if="item.type === 'str' && (typeof configValues[item.key] === 'string' && configValues[item.key].length > 100)"
                  :value="String(configValues[item.key] ?? '')"
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm font-mono focus:outline-none focus:ring-1 focus:ring-blue-500/50 resize-y min-h-[100px]"
                  @input="configValues[item.key] = ($event.target as HTMLTextAreaElement).value"
                />
                
                <!-- 数字和普通字符串使用 input -->
                <input
                  v-else
                  :value="String(configValues[item.key] ?? '')"
                  :type="item.type === 'int' || item.type === 'float' ? 'number' : 'text'"
                  :step="item.type === 'float' ? '0.1' : undefined"
                  class="w-full px-3 py-2 rounded-lg bg-bg-elevated border border-border text-text-primary text-sm focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                  :class="item.is_sensitive ? 'font-mono' : ''"
                  :placeholder="item.is_sensitive ? maskSensitiveValue(configValues[item.key], true) : ''"
                  @input="(e) => { const val = (e.target as HTMLInputElement).value; if (item.type === 'int') configValues[item.key] = parseInt(val, 10) || 0; else if (item.type === 'float') configValues[item.key] = parseFloat(val) || 0; else configValues[item.key] = val; }"
                />
                
                    <!-- 显示默认值提示 -->
                    <div v-if="configDefaults[item.key] !== undefined && configValues[item.key] !== configDefaults[item.key]" class="text-[10px] text-text-muted italic">
                      默认值: {{ typeof configDefaults[item.key] === 'object' ? JSON.stringify(configDefaults[item.key]) : String(configDefaults[item.key]) }}
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
