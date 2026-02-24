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

defineOptions({ name: 'AdminIdeaSystemConfigView' })

const router = useRouter()

// ---------------------------------------------------------------------------
// Module definitions
// ---------------------------------------------------------------------------

const configModules = [
  {
    key: 'idea_ingest',
    label: '原子抽取 (idea_ingest)',
    icon: '⚗️',
    desc: '从论文全文抽取结构化灵感原子',
    llmPrefix: 'idea_ingest',
    prompts: [{ variable: 'idea_ingest_system_prompt', label: '原子抽取提示词' }],
  },
  {
    key: 'idea_question',
    label: '研究问题生成 (idea_question)',
    icon: '❓',
    desc: '从局限性原子挖掘有价值的研究问题',
    llmPrefix: 'idea_question',
    prompts: [{ variable: 'idea_question_system_prompt', label: '研究问题生成提示词' }],
  },
  {
    key: 'idea_candidate',
    label: '灵感候选生成 (idea_candidate)',
    icon: '💡',
    desc: '基于研究问题与原子生成多策略灵感候选',
    llmPrefix: 'idea_candidate',
    prompts: [{ variable: 'idea_candidate_system_prompt', label: '灵感候选生成提示词' }],
  },
  {
    key: 'idea_review',
    label: '灵感评审 (idea_review)',
    icon: '🔍',
    desc: '多视角评委对灵感候选进行评审打分',
    llmPrefix: 'idea_review',
    prompts: [{ variable: 'idea_review_system_prompt', label: '灵感评审提示词' }],
  },
  {
    key: 'idea_revise',
    label: '灵感修订 (idea_revise)',
    icon: '✏️',
    desc: '根据评审反馈自动修订灵感候选',
    llmPrefix: 'idea_revise',
    prompts: [{ variable: 'idea_revise_system_prompt', label: '灵感修订提示词' }],
  },
  {
    key: 'idea_plan',
    label: '实验计划生成 (idea_plan)',
    icon: '📋',
    desc: '为通过评审的灵感生成可执行实验计划',
    llmPrefix: 'idea_plan',
    prompts: [{ variable: 'idea_plan_system_prompt', label: '实验计划生成提示词' }],
  },
  {
    key: 'idea_eval',
    label: '评测回放 (idea_eval)',
    icon: '🔁',
    desc: '对问题集重新生成灵感用于历史版本对比',
    llmPrefix: 'idea_eval',
    prompts: [{ variable: 'idea_eval_system_prompt', label: '评测回放提示词' }],
  },
]

const prefixModelKey: Record<string, string> = {
  idea_ingest:    'idea_ingest_model',
  idea_question:  'idea_question_model',
  idea_candidate: 'idea_candidate_model',
  idea_review:    'idea_review_model',
  idea_revise:    'idea_revise_model',
  idea_plan:      'idea_plan_model',
  idea_eval:      'idea_eval_model',
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
  idea_ingest: null,
  idea_question: null,
  idea_candidate: null,
  idea_review: null,
  idea_revise: null,
  idea_plan: null,
  idea_eval: null,
})

const selectedPromptIds = reactive<Record<string, number | null>>({
  idea_ingest_system_prompt: null,
  idea_question_system_prompt: null,
  idea_candidate_system_prompt: null,
  idea_review_system_prompt: null,
  idea_revise_system_prompt: null,
  idea_plan_system_prompt: null,
  idea_eval_system_prompt: null,
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
    const currentModel = configValues.value[prefixModelKey[mod.llmPrefix]]
    const match = llmConfigs.value.find(c => c.model === currentModel)
    selectedLlmIds[mod.llmPrefix] = match?.id ?? null

    for (const p of mod.prompts) {
      const currentPrompt = configValues.value[p.variable]
      const matchP = promptConfigs.value.find(c => c.prompt_content === currentPrompt)
      selectedPromptIds[p.variable] = matchP?.id ?? null
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
    selectedLlmIds[mod.llmPrefix] = quickFillLlmId.value
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
    const id = selectedLlmIds[mod.llmPrefix]
    if (id && id !== originalLlmIds.value[mod.llmPrefix]) {
      llmApplies.push({ config_id: id, prefix: mod.llmPrefix })
    }
    for (const p of mod.prompts) {
      const pid = selectedPromptIds[p.variable]
      if (pid && pid !== originalPromptIds.value[p.variable]) {
        promptApplies.push({ config_id: pid, variable: p.variable })
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
        <h1 class="text-lg font-bold text-text-primary flex-1">灵感生成系统配置</h1>
        <button
          class="px-4 py-1.5 rounded-full text-sm font-semibold border-none text-white active:opacity-80 transition-opacity disabled:opacity-50"
          style="background: linear-gradient(135deg, #ea580c, #f97316)"
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
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#f97316] border-r-[#fb923c] animate-spin"></div>
        </div>
      </div>

      <template v-else>
        <!-- Status messages -->
        <div v-if="saveSuccess || saveError" class="mx-4 mt-3 px-4 py-2.5 rounded-xl text-sm" :class="saveSuccess ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'">
          {{ saveSuccess ? '✓ 配置已保存' : saveError }}
        </div>

        <!-- Quick fill section -->
        <div class="mx-4 mt-4 rounded-2xl bg-orange-500/8 border border-orange-500/20 overflow-hidden">
          <div class="px-4 py-3 border-b border-orange-500/15 flex items-center gap-2">
            <span class="text-base">⚡</span>
            <span class="text-sm font-semibold text-orange-300">全局快捷设置</span>
          </div>
          <div class="px-4 py-3 space-y-3">
            <div class="flex items-center gap-2">
              <span class="text-xs text-text-secondary w-16 shrink-0">统一模型</span>
              <select
                v-model="quickFillLlmId"
                class="flex-1 min-w-0 px-3 py-2 bg-bg-elevated border border-border rounded-xl text-sm text-text-primary focus:outline-none focus:border-orange-500 transition-colors"
              >
                <option :value="null">— 选择模型 —</option>
                <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
              </select>
              <button
                :disabled="!quickFillLlmId"
                class="shrink-0 px-3 py-2 rounded-xl text-xs font-medium bg-orange-600 text-white border-none active:opacity-80 disabled:opacity-40 transition-opacity"
                @click="applyQuickFillLlm"
              >全填</button>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs text-text-secondary w-16 shrink-0">统一提示词</span>
              <select
                v-model="quickFillPromptId"
                class="flex-1 min-w-0 px-3 py-2 bg-bg-elevated border border-border rounded-xl text-sm text-text-primary focus:outline-none focus:border-orange-400 transition-colors"
              >
                <option :value="null">— 选择提示词 —</option>
                <option v-for="cfg in promptConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
              </select>
              <button
                :disabled="!quickFillPromptId"
                class="shrink-0 px-3 py-2 rounded-xl text-xs font-medium bg-orange-500 text-white border-none active:opacity-80 disabled:opacity-40 transition-opacity"
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
          <div class="px-4 py-3 border-b border-border bg-bg-elevated/40 flex items-center gap-2">
            <span class="text-base">{{ mod.icon }}</span>
            <div class="flex-1 min-w-0">
              <h3 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h3>
              <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
            </div>
          </div>

          <div class="divide-y divide-border/40">
            <!-- LLM row -->
            <div class="px-4 py-3">
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
                <option :value="null">— 未配置（继承全局）—</option>
                <option v-for="cfg in llmConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
              </select>
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
                <option :value="null">— 未配置（使用系统默认）—</option>
                <option v-for="cfg in promptConfigs" :key="cfg.id" :value="cfg.id">{{ cfg.name }}</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Bottom save button -->
        <div class="mx-4 mt-6">
          <button
            class="w-full py-3.5 rounded-2xl text-base font-semibold border-none transition-opacity disabled:opacity-50 active:opacity-80"
            :class="dirtyCount > 0 ? 'text-white' : 'text-text-secondary'"
            :style="dirtyCount > 0
              ? 'background: linear-gradient(135deg, #ea580c, #f97316); box-shadow: 0 8px 20px #f9731633'
              : 'background: var(--color-bg-elevated)'"
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
