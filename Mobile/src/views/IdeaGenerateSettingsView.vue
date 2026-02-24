<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchUserSettings, saveUserSettings,
  fetchUserLlmPresets, fetchUserPromptPresets,
} from '../api'
import type { UserLlmPreset, UserPromptPreset } from '../api'

defineOptions({ name: 'IdeaGenerateSettingsView' })

const router = useRouter()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const loading = ref(false)
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')

const form = reactive<Record<string, any>>({})
const llmPresets = ref<UserLlmPreset[]>([])
const promptPresets = ref<UserPromptPreset[]>([])

// ---------------------------------------------------------------------------
// Module definitions (mirrors Web ProfileSettings ideaModules)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------

async function load() {
  loading.value = true
  saveError.value = ''
  try {
    const [settingsRes, llmRes, promptRes] = await Promise.all([
      fetchUserSettings('idea_generate'),
      fetchUserLlmPresets(),
      fetchUserPromptPresets(),
    ])
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, settingsRes.settings || {})
    llmPresets.value = llmRes.presets
    promptPresets.value = promptRes.presets
  } catch (e: any) {
    saveError.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// Save
// ---------------------------------------------------------------------------

async function handleSave() {
  saving.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    const res = await saveUserSettings('idea_generate', { ...form })
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, res.settings || {})
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 2500)
  } catch (e: any) {
    saveError.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

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
        <h1 class="text-lg font-bold text-text-primary flex-1">灵感生成配置</h1>
        <button
          class="px-4 py-1.5 rounded-full text-sm font-semibold border-none text-white active:opacity-80 transition-opacity disabled:opacity-50"
          style="background: linear-gradient(135deg, #ea580c, #f97316)"
          :disabled="saving"
          @click="handleSave"
        >
          {{ saving ? '保存中' : '保存' }}
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto pb-8">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center h-48">
        <div class="relative w-10 h-10 flex items-center justify-center">
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#f97316] border-r-[#fb923c] animate-spin"></div>
        </div>
      </div>

      <template v-else>
        <!-- Save status -->
        <div v-if="saveSuccess || saveError" class="mx-4 mt-3 px-4 py-2.5 rounded-xl text-sm" :class="saveSuccess ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'">
          {{ saveSuccess ? '✓ 设置已保存' : saveError }}
        </div>

        <!-- Global LLM config -->
        <div class="mx-4 mt-4 rounded-2xl bg-bg-card border border-border overflow-hidden">
          <div class="px-4 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-2">
            <span class="text-base">🌐</span>
            <div class="flex-1 min-w-0">
              <h3 class="text-sm font-semibold text-text-primary">全局默认模型</h3>
              <p class="text-[11px] text-text-muted">各阶段未单独配置时使用；留空则需手动填 URL/Key/Model</p>
            </div>
          </div>

          <div class="px-4 py-4">
            <label class="block text-xs font-medium text-text-secondary mb-2">选择模型预设</label>
            <div class="flex flex-wrap gap-2 mb-3">
              <button
                class="px-3 py-1.5 rounded-full text-xs font-medium border transition-all"
                :class="!form.llm_preset_id ? 'border-transparent text-white' : 'border-border text-text-secondary bg-transparent'"
                :style="!form.llm_preset_id ? { background: 'linear-gradient(135deg, #ea580c, #f97316)' } : {}"
                @click="form.llm_preset_id = ''"
              >手动配置</button>
              <button
                v-for="preset in llmPresets"
                :key="preset.id"
                class="px-3 py-1.5 rounded-full text-xs font-medium border transition-all"
                :class="String(form.llm_preset_id) === String(preset.id) ? 'border-transparent text-white' : 'border-border text-text-secondary bg-transparent'"
                :style="String(form.llm_preset_id) === String(preset.id) ? { background: 'linear-gradient(135deg, #ea580c, #f97316)' } : {}"
                @click="form.llm_preset_id = preset.id"
              >{{ preset.name }}</button>
            </div>

            <!-- Manual fields -->
            <div v-if="!form.llm_preset_id" class="space-y-3">
              <div>
                <label class="block text-xs text-text-secondary mb-1">API URL</label>
                <input v-model="form.llm_base_url" type="text" placeholder="https://api.openai.com/v1" class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-xl text-sm focus:outline-none focus:border-[#f97316] transition-colors" />
              </div>
              <div>
                <label class="block text-xs text-text-secondary mb-1">API Key</label>
                <input v-model="form.llm_api_key" type="password" placeholder="sk-..." class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-xl text-sm font-mono focus:outline-none focus:border-[#f97316] transition-colors" />
              </div>
              <div>
                <label class="block text-xs text-text-secondary mb-1">Model</label>
                <input v-model="form.llm_model" type="text" placeholder="gpt-4o / qwen-plus" class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-xl text-sm focus:outline-none focus:border-[#f97316] transition-colors" />
              </div>
            </div>
          </div>
        </div>

        <!-- Per-module config cards -->
        <div v-for="mod in ideaModules" :key="mod.key" class="mx-4 mt-3 rounded-2xl bg-bg-card border border-border overflow-hidden">
          <!-- Module header -->
          <div class="px-4 py-3.5 border-b border-border bg-bg-elevated/40 flex items-center gap-2">
            <span class="text-base">{{ mod.icon }}</span>
            <div class="flex-1 min-w-0">
              <h3 class="text-sm font-semibold text-text-primary">{{ mod.label }}</h3>
              <p class="text-[11px] text-text-muted">{{ mod.desc }}</p>
            </div>
          </div>

          <div class="divide-y divide-border/40">
            <!-- Module-specific LLM preset (only for modules that have their own key) -->
            <div v-if="mod.llmFormKey !== 'llm_preset_id'" class="px-4 py-3.5">
              <div class="flex items-center gap-1 mb-2">
                <span class="text-sm">🤖</span>
                <span class="text-xs font-medium text-text-secondary">专用模型预设</span>
              </div>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="preset in llmPresets"
                  :key="preset.id"
                  class="px-2.5 py-1 rounded-full text-xs font-medium border transition-all"
                  :class="String(form[mod.llmFormKey]) === String(preset.id) ? 'border-transparent text-white' : 'border-border text-text-secondary bg-transparent'"
                  :style="String(form[mod.llmFormKey]) === String(preset.id) ? { background: 'linear-gradient(135deg, #ea580c, #f97316)' } : {}"
                  @click="form[mod.llmFormKey] = preset.id"
                >{{ preset.name }}</button>
                <button
                  v-if="form[mod.llmFormKey]"
                  class="px-2.5 py-1 rounded-full text-xs border border-border/60 text-text-muted hover:text-red-400 transition-colors"
                  @click="form[mod.llmFormKey] = null"
                >✕ 清除</button>
                <span v-if="llmPresets.length === 0" class="text-[11px] text-text-muted/60 italic pt-1">暂无预设，请前往 Web 端创建</span>
              </div>
              <p v-if="!form[mod.llmFormKey]" class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用全局默认配置</p>
            </div>

            <!-- Prompt preset rows -->
            <div v-for="prompt in mod.prompts" :key="prompt.formKey" class="px-4 py-3.5">
              <div class="flex items-center gap-1 mb-2">
                <span class="text-sm">📝</span>
                <span class="text-xs font-medium text-text-secondary">{{ prompt.label }}</span>
              </div>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="preset in promptPresets"
                  :key="preset.id"
                  class="px-2.5 py-1 rounded-full text-xs font-medium border transition-all"
                  :class="String(form[prompt.formKey]) === String(preset.id) ? 'border-transparent text-white bg-gradient-to-r from-[#ea580c] to-[#f97316]' : 'border-border text-text-secondary bg-transparent'"
                  @click="form[prompt.formKey] = preset.id"
                >{{ preset.name }}</button>
                <button
                  v-if="form[prompt.formKey]"
                  class="px-2.5 py-1 rounded-full text-xs border border-border/60 text-text-muted transition-colors"
                  @click="form[prompt.formKey] = null"
                >✕ 清除</button>
                <span v-if="promptPresets.length === 0" class="text-[11px] text-text-muted/60 italic pt-1">暂无预设，请前往 Web 端创建</span>
              </div>
              <p v-if="!form[prompt.formKey]" class="text-[11px] text-text-muted/50 mt-1.5 italic">未选择，使用系统默认提示词</p>
            </div>
          </div>
        </div>

        <!-- Bottom save button -->
        <div class="mx-4 mt-6">
          <button
            class="w-full py-3.5 rounded-2xl text-base font-semibold text-white border-none transition-opacity disabled:opacity-50 active:opacity-80"
            style="background: linear-gradient(135deg, #ea580c, #f97316); box-shadow: 0 8px 20px #f9731633"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? '保存中...' : '保存配置' }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
