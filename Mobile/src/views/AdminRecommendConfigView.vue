<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  adminFetchSystemConfig,
  adminFetchLlmConfigs,
  adminFetchPromptConfigs,
  adminBatchApplyConfigs,
} from '../api'
import type { AdminLlmConfig, AdminPromptConfig } from '../api'

defineOptions({ name: 'AdminRecommendConfigView' })

const router = useRouter()

// ---------------------------------------------------------------------------
// Module definitions
// ---------------------------------------------------------------------------

const configModules = [
  {
    key: 'theme_select',
    label: '主题相关性评分',
    icon: '🎯',
    desc: '对论文进行主题相关性评分，筛选相关论文',
    llmPrefix: 'theme_select' as string | null,
    prompts: [{ variable: 'theme_select_system_prompt', label: '评分提示词' }],
  },
  {
    key: 'org',
    label: '机构判别',
    icon: '🏛️',
    desc: '提取论文作者机构信息',
    llmPrefix: 'org' as string | null,
    prompts: [{ variable: 'pdf_info_system_prompt', label: '机构判别提示词' }],
  },
  {
    key: 'summary',
    label: '摘要生成',
    icon: '📄',
    desc: '生成论文中文摘要笔记',
    llmPrefix: 'summary' as string | null,
    prompts: [{ variable: 'system_prompt', label: '摘要生成提示词' }],
  },
  {
    key: 'summary_limit',
    label: '摘要精简',
    icon: '✂️',
    desc: '压缩摘要各部分至字数上限',
    llmPrefix: 'summary_limit' as string | null,
    prompts: [
      { variable: 'summary_limit_prompt_intro', label: '文章简介精简' },
      { variable: 'summary_limit_prompt_method', label: '重点思路精简' },
      { variable: 'summary_limit_prompt_findings', label: '分析总结精简' },
      { variable: 'summary_limit_prompt_opinion', label: '个人观点精简' },
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
    prompts: [{ variable: 'summary_batch_system_prompt', label: '批量摘要提示词' }],
  },
  {
    key: 'paper_assets',
    label: '论文结构化抽取',
    icon: '🔬',
    desc: '提取论文结构化数据',
    llmPrefix: null,
    prompts: [{ variable: 'paper_assets_system_prompt', label: '结构化抽取提示词' }],
  },
]

const prefixModelKey: Record<string, string> = {
  theme_select: 'theme_select_model',
  org: 'org_model',
  summary: 'summary_model',
  summary_limit: 'summary_limit_model',
  summary_batch: 'summary_batch_model',
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const loading = ref(false)
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')

const llmConfigs = ref<AdminLlmConfig[]>([])
const promptConfigs = ref<AdminPromptConfig[]>([])
const configValues = ref<Record<string, any>>({})

const selectedLlmIds = reactive<Record<string, number | null>>({
  theme_select: null,
  org: null,
  summary: null,
  summary_limit: null,
  summary_batch: null,
})

const selectedPromptIds = reactive<Record<string, number | null>>({
  theme_select_system_prompt: null,
  pdf_info_system_prompt: null,
  system_prompt: null,
  summary_limit_prompt_intro: null,
  summary_limit_prompt_method: null,
  summary_limit_prompt_findings: null,
  summary_limit_prompt_opinion: null,
  summary_limit_prompt_structure_check: null,
  summary_limit_prompt_structure_rewrite: null,
  summary_limit_prompt_headline: null,
  summary_batch_system_prompt: null,
  paper_assets_system_prompt: null,
})

const originalLlmIds = ref<Record<string, number | null>>({})
const originalPromptIds = ref<Record<string, number | null>>({})

const quickFillLlmId = ref<number | null>(null)
const quickFillPromptId = ref<number | null>(null)

// ---------------------------------------------------------------------------
// Dirty count
// ---------------------------------------------------------------------------

const dirtyCount = computed(() => {
  let n = 0
  for (const [k, v] of Object.entries(selectedLlmIds)) {
    if (v !== originalLlmIds.value[k]) n++
  }
  for (const [k, v] of Object.entries(selectedPromptIds)) {
    if (v !== originalPromptIds.value[k]) n++
  }
  return n
})

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------

function detectSelections() {
  for (const mod of configModules) {
    if (mod.llmPrefix) {
      const currentModel = configValues.value[prefixModelKey[mod.llmPrefix]]
      const match = llmConfigs.value.find(c => c.model === currentModel)
      selectedLlmIds[mod.llmPrefix] = match?.id ?? null
    }
    for (const p of mod.prompts) {
      const currentPrompt = configValues.value[p.variable]
      const match = promptConfigs.value.find(c => c.prompt_content === currentPrompt)
      selectedPromptIds[p.variable] = match?.id ?? null
    }
  }
  originalLlmIds.value = { ...selectedLlmIds }
  originalPromptIds.value = { ...selectedPromptIds }
}

async function load() {
  loading.value = true
  saveError.value = ''
  try {
    const [sysRes, llmRes, promptRes] = await Promise.all([
      adminFetchSystemConfig(),
      adminFetchLlmConfigs(),
      adminFetchPromptConfigs(),
    ])
    // flatten config values
    const vals: Record<string, any> = {}
    for (const group of sysRes.groups) {
      for (const item of group.items) {
        vals[item.key] = item.value
      }
    }
    configValues.value = vals
    llmConfigs.value = llmRes.configs
    promptConfigs.value = promptRes.configs
    detectSelections()
  } catch (e: any) {
    saveError.value = e?.response?.data?.detail || '加载失败'
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// Quick fill
// ---------------------------------------------------------------------------

function applyQuickFillLlm() {
  if (!quickFillLlmId.value) return
  for (const mod of configModules) {
    if (mod.llmPrefix) selectedLlmIds[mod.llmPrefix] = quickFillLlmId.value
  }
}

function applyQuickFillPrompt() {
  if (!quickFillPromptId.value) return
  for (const mod of configModules) {
    for (const p of mod.prompts) {
      selectedPromptIds[p.variable] = quickFillPromptId.value
    }
  }
}

// ---------------------------------------------------------------------------
// Save
// ---------------------------------------------------------------------------

async function handleSave() {
  const llmApplies: { config_id: number; prefix: string }[] = []
  const promptApplies: { config_id: number; variable: string }[] = []

  for (const mod of configModules) {
    if (mod.llmPrefix) {
      const id = selectedLlmIds[mod.llmPrefix]
      if (id && id !== originalLlmIds.value[mod.llmPrefix]) {
        llmApplies.push({ config_id: id, prefix: mod.llmPrefix })
      }
    }
    for (const p of mod.prompts) {
      const id = selectedPromptIds[p.variable]
      if (id && id !== originalPromptIds.value[p.variable]) {
        promptApplies.push({ config_id: id, variable: p.variable })
      }
    }
  }

  if (llmApplies.length === 0 && promptApplies.length === 0) {
    saveError.value = '没有需要保存的更改'
    setTimeout(() => { saveError.value = '' }, 2000)
    return
  }

  saving.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    await adminBatchApplyConfigs(llmApplies, promptApplies)
    await load()
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 2500)
  } catch (e: any) {
    saveError.value = e?.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="h-full flex flex-col bg-bg-base">
    <!-- Header -->
    <div class="shrink-0 safe-area-top">
      <div class="flex items-center gap-3 px-4 pt-4 pb-3">
        <button
          class="w-9 h-9 rounded-full bg-bg-elevated flex items-center justify-center active:bg-bg-hover transition-colors border-none"
          @click="router.back()"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-text-primary">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <h1 class="text-lg font-bold text-text-primary flex-1">论文推荐配置</h1>
        <button
          class="px-4 py-1.5 rounded-full text-sm font-semibold border-none text-white active:opacity-80 transition-opacity disabled:opacity-50"
          style="background: linear-gradient(135deg, #2563eb, #3b82f6)"
          :disabled="saving"
          @click="handleSave"
        >
          {{ saving ? '保存中' : dirtyCount > 0 ? `保存 (${dirtyCount})` : '保存' }}
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto pb-8">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center h-48">
        <div class="w-10 h-10 relative flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-blue-500 border-r-blue-400 animate-spin"></div>
        </div>
      </div>

      <template v-else>
        <!-- Status messages -->
        <div v-if="saveSuccess || saveError" class="mx-4 mt-3 px-4 py-2.5 rounded-xl text-sm" :class="saveSuccess ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'">
          {{ saveSuccess ? '✓ 配置已保存' : saveError }}
        </div>

        <!-- Quick fill section -->
        <div class="mx-4 mt-4 rounded-2xl bg-blue-500/8 border border-blue-500/20 overflow-hidden">
          <div class="px-4 py-3 border-b border-blue-500/15 flex items-center gap-2">
            <span class="text-base">⚡</span>
            <span class="text-sm font-semibold text-blue-300">全局快捷设置</span>
          </div>
          <div class="px-4 py-3 space-y-3">
            <!-- Quick fill LLM -->
            <div class="flex items-center gap-2">
              <span class="text-xs text-text-secondary w-16 shrink-0">统一模型</span>
              <select
                v-model="quickFillLlmId"
                class="flex-1 min-w-0 px-3 py-2 bg-bg-elevated border border-border rounded-xl text-sm text-text-primary focus:outline-none focus:border-blue-500 transition-colors"
              >
                <option :value="null">— 选择模型 —</option>
                <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
              </select>
              <button
                :disabled="!quickFillLlmId"
                class="shrink-0 px-3 py-2 rounded-xl text-xs font-medium bg-blue-600 text-white border-none active:opacity-80 disabled:opacity-40 transition-opacity"
                @click="applyQuickFillLlm"
              >全填</button>
            </div>
            <!-- Quick fill prompt -->
            <div class="flex items-center gap-2">
              <span class="text-xs text-text-secondary w-16 shrink-0">统一提示词</span>
              <select
                v-model="quickFillPromptId"
                class="flex-1 min-w-0 px-3 py-2 bg-bg-elevated border border-border rounded-xl text-sm text-text-primary focus:outline-none focus:border-purple-500 transition-colors"
              >
                <option :value="null">— 选择提示词 —</option>
                <option v-for="cfg in promptConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
              </select>
              <button
                :disabled="!quickFillPromptId"
                class="shrink-0 px-3 py-2 rounded-xl text-xs font-medium bg-purple-600 text-white border-none active:opacity-80 disabled:opacity-40 transition-opacity"
                @click="applyQuickFillPrompt"
              >全填</button>
            </div>
          </div>
        </div>

        <!-- Empty config library prompt -->
        <div v-if="llmConfigs.length === 0 || promptConfigs.length === 0" class="mx-4 mt-3 space-y-2">
          <div v-if="llmConfigs.length === 0" class="px-4 py-3 rounded-2xl border border-dashed border-border bg-bg-card text-xs text-text-muted text-center">
            暂无模型配置，请在 Web 端管理员界面创建
          </div>
          <div v-if="promptConfigs.length === 0" class="px-4 py-3 rounded-2xl border border-dashed border-border bg-bg-card text-xs text-text-muted text-center">
            暂无提示词配置，请在 Web 端管理员界面创建
          </div>
        </div>

        <!-- Module cards -->
        <div v-for="mod in configModules" :key="mod.key" class="mx-4 mt-3 rounded-2xl bg-bg-card border border-border overflow-hidden">
          <!-- Module header -->
          <div class="px-4 py-3 border-b border-border bg-bg-elevated/40 flex items-center gap-2">
            <span class="text-base">{{ mod.icon }}</span>
            <div class="flex-1 min-w-0">
              <h3 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h3>
              <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
            </div>
          </div>

          <div class="divide-y divide-border/40">
            <!-- LLM row -->
            <div v-if="mod.llmPrefix" class="px-4 py-3">
              <div class="flex items-center gap-1.5 mb-2">
                <span
                  class="w-1.5 h-1.5 rounded-full shrink-0"
                  :class="selectedLlmIds[mod.llmPrefix] !== originalLlmIds[mod.llmPrefix] ? 'bg-amber-400' : 'bg-transparent'"
                ></span>
                <span class="text-xs font-medium text-text-secondary">🤖 调用模型</span>
              </div>
              <select
                v-model="selectedLlmIds[mod.llmPrefix]"
                class="w-full px-3 py-2 bg-bg-elevated border rounded-xl text-sm text-text-primary focus:outline-none transition-colors"
                :class="selectedLlmIds[mod.llmPrefix] !== originalLlmIds[mod.llmPrefix] ? 'border-amber-500/60' : 'border-border'"
              >
                <option :value="null">— 未配置 —</option>
                <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
              </select>
              <p v-if="!selectedLlmIds[mod.llmPrefix]" class="text-[11px] text-text-muted/50 mt-1 italic">未选择</p>
            </div>

            <!-- Prompt rows -->
            <div v-for="prompt in mod.prompts" :key="prompt.variable" class="px-4 py-3">
              <div class="flex items-center gap-1.5 mb-2">
                <span
                  class="w-1.5 h-1.5 rounded-full shrink-0"
                  :class="selectedPromptIds[prompt.variable] !== originalPromptIds[prompt.variable] ? 'bg-amber-400' : 'bg-transparent'"
                ></span>
                <span class="text-xs font-medium text-text-secondary">📝 {{ prompt.label }}</span>
              </div>
              <select
                v-model="selectedPromptIds[prompt.variable]"
                class="w-full px-3 py-2 bg-bg-elevated border rounded-xl text-sm text-text-primary focus:outline-none transition-colors"
                :class="selectedPromptIds[prompt.variable] !== originalPromptIds[prompt.variable] ? 'border-amber-500/60' : 'border-border'"
              >
                <option :value="null">— 未配置 —</option>
                <option v-for="cfg in promptConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
              </select>
              <p v-if="!selectedPromptIds[prompt.variable]" class="text-[11px] text-text-muted/50 mt-1 italic">未选择，使用系统默认</p>
            </div>
          </div>
        </div>

        <!-- Bottom save button -->
        <div class="mx-4 mt-6">
          <button
            class="w-full py-3.5 rounded-2xl text-base font-semibold text-white border-none transition-opacity disabled:opacity-50 active:opacity-80"
            :style="dirtyCount > 0
              ? 'background: linear-gradient(135deg, #2563eb, #3b82f6); box-shadow: 0 8px 20px #3b82f633'
              : 'background: var(--color-bg-elevated); color: var(--color-text-secondary)'"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? '保存中...' : dirtyCount > 0 ? `保存 ${dirtyCount} 项更改` : '配置已是最新' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
