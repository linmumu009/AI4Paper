<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { fetchUserSettings, saveUserSettings } from '../api'
import { currentUser } from '../stores/auth'

// ---------------------------------------------------------------------------
// Sidebar navigation
// ---------------------------------------------------------------------------

interface NavItem {
  key: string
  label: string
  icon: string
  enabled: boolean
}

const navItems: NavItem[] = [
  { key: 'compare', label: '对比分析', icon: 'compare', enabled: true },
  { key: 'inspiration', label: '灵感涌现', icon: 'lightbulb', enabled: true },
  { key: 'paper_summary', label: '论文解读', icon: 'article', enabled: false },
  { key: 'theme_filter', label: '主题筛选', icon: 'filter', enabled: false },
]

const activeNav = ref('compare')

// ---------------------------------------------------------------------------
// Settings state
// ---------------------------------------------------------------------------

// Form data for the active feature
const form = reactive<Record<string, any>>({})
const defaults = ref<Record<string, any>>({})
const loading = ref(false)
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref('')

// API Key visibility
const showApiKey = ref(false)

// ---------------------------------------------------------------------------
// Load settings
// ---------------------------------------------------------------------------

async function loadSettings(feature: string) {
  loading.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    const res = await fetchUserSettings(feature)
    defaults.value = res.defaults || {}
    // Fill form with current settings
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, res.settings || {})
  } catch (e: any) {
    saveError.value = e?.message || '加载设置失败'
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// Save settings
// ---------------------------------------------------------------------------

async function handleSave() {
  saving.value = true
  saveError.value = ''
  saveSuccess.value = false
  try {
    // Only save fields that differ from defaults (or are no-default fields)
    const toSave: Record<string, any> = { ...form }
    const res = await saveUserSettings(activeNav.value, toSave)
    // Refresh with merged result
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

// ---------------------------------------------------------------------------
// Reset to default
// ---------------------------------------------------------------------------

function resetField(key: string) {
  if (key in defaults.value) {
    form[key] = defaults.value[key]
  }
}

// ---------------------------------------------------------------------------
// Computed helpers
// ---------------------------------------------------------------------------

const isLlmConfigured = computed(() => {
  return !!(form.llm_base_url?.trim() && form.llm_api_key?.trim() && form.llm_model?.trim())
})

const hasChanges = computed(() => {
  // Simple check: always allow saving
  return true
})

// No-default keys (these fields don't have a "restore default" button)
const noDefaultKeys = new Set(['llm_base_url', 'llm_api_key', 'llm_model'])

function hasDefault(key: string): boolean {
  return !noDefaultKeys.has(key) && key in defaults.value
}

function isDefault(key: string): boolean {
  if (!hasDefault(key)) return false
  return form[key] === defaults.value[key]
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMounted(() => {
  loadSettings(activeNav.value)
})

watch(activeNav, (feature) => {
  loadSettings(feature)
})
</script>

<template>
  <div class="h-full flex overflow-hidden">
    <!-- Left sidebar navigation -->
    <aside class="w-56 h-full bg-bg-sidebar border-r border-border flex flex-col shrink-0">
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

      <!-- Nav items -->
      <nav class="flex-1 overflow-y-auto py-2">
        <button
          v-for="item in navItems"
          :key="item.key"
          class="w-full px-4 py-2.5 text-left text-sm flex items-center gap-3 transition-colors"
          :class="[
            item.enabled
              ? (activeNav === item.key
                  ? 'bg-bg-elevated text-text-primary font-medium'
                  : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary cursor-pointer')
              : 'text-text-muted cursor-not-allowed opacity-50',
          ]"
          :disabled="!item.enabled"
          @click="item.enabled && (activeNav = item.key)"
        >
          <!-- Icons -->
          <svg v-if="item.icon === 'compare'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
          </svg>
          <svg v-else-if="item.icon === 'article'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
          </svg>
          <svg v-else-if="item.icon === 'lightbulb'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 18h6" /><path d="M10 22h4" /><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
          </svg>
          <svg v-else-if="item.icon === 'filter'" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
          </svg>

          <span>{{ item.label }}</span>
          <span v-if="!item.enabled" class="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-bg-elevated text-text-muted">即将推出</span>
        </button>
      </nav>
    </aside>

    <!-- Right content area -->
    <div class="flex-1 h-full overflow-y-auto">
      <!-- Loading state -->
      <div v-if="loading" class="flex items-center justify-center h-full">
        <div class="text-center">
          <div class="relative w-12 h-12 mx-auto mb-3 flex items-center justify-center">
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-[#6366f1] border-r-[#8b5cf6] animate-spin"></div>
          </div>
          <p class="text-sm text-text-muted">加载设置...</p>
        </div>
      </div>

      <!-- Compare settings form -->
      <div v-else-if="activeNav === 'compare'" class="max-w-2xl mx-auto px-8 py-8">
        <!-- Section title -->
        <div class="mb-8">
          <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#8b5cf6]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
            </svg>
            对比分析设置
          </h2>
          <p class="text-xs text-text-muted mt-1">配置论文对比分析所使用的大语言模型参数</p>
        </div>

        <!-- LLM Connection status banner -->
        <div
          class="mb-6 px-4 py-3 rounded-lg border text-sm flex items-center gap-2"
          :class="isLlmConfigured
            ? 'bg-tinder-green/10 border-tinder-green/30 text-tinder-green'
            : 'bg-tinder-pink/10 border-tinder-pink/30 text-tinder-pink'"
        >
          <svg v-if="isLlmConfigured" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>
            {{ isLlmConfigured ? 'LLM 已配置，对比分析功能可用' : 'LLM 未配置，请填写以下连接信息以启用对比分析' }}
          </span>
        </div>

        <!-- LLM Connection section -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
          <legend class="px-2 text-xs font-semibold text-text-secondary">LLM 连接配置</legend>

          <!-- LLM Base URL -->
          <div class="mb-5">
            <label class="block text-xs font-medium text-text-secondary mb-1.5">API URL</label>
            <div class="flex items-center gap-2">
              <input
                v-model="form.llm_base_url"
                type="text"
                placeholder="例如: https://api.openai.com/v1"
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors"
              />
            </div>
          </div>

          <!-- LLM API Key -->
          <div class="mb-5">
            <label class="block text-xs font-medium text-text-secondary mb-1.5">API Key</label>
            <div class="flex items-center gap-2">
              <div class="flex-1 relative">
                <input
                  v-model="form.llm_api_key"
                  :type="showApiKey ? 'text' : 'password'"
                  placeholder="sk-..."
                  class="w-full px-3 py-2 pr-10 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors font-mono"
                />
                <button
                  type="button"
                  class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-secondary transition-colors"
                  @click="showApiKey = !showApiKey"
                  :title="showApiKey ? '隐藏' : '显示'"
                >
                  <svg v-if="showApiKey" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                  </svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <!-- LLM Model -->
          <div>
            <label class="block text-xs font-medium text-text-secondary mb-1.5">Model</label>
            <div class="flex items-center gap-2">
              <input
                v-model="form.llm_model"
                type="text"
                placeholder="例如: gpt-4o, claude-sonnet-4-20250514, qwen-plus"
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors"
              />
            </div>
          </div>
        </fieldset>

        <!-- Data Source section -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
          <legend class="px-2 text-xs font-semibold text-text-secondary">数据源配置</legend>

          <div>
            <label class="block text-xs font-medium text-text-secondary mb-1.5">对比分析数据源</label>
            <div class="flex items-center gap-2">
              <select
                v-model="form.data_source"
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors appearance-none cursor-pointer"
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
            <p class="text-[11px] text-text-muted mt-1">默认值: {{ { full_text: '全文', abstract: '原文摘要', summary: '系统总结' }[defaults.data_source] || defaults.data_source }}. 选择 LLM 对比分析时使用的论文内容来源。</p>
            <div class="mt-3 text-[11px] text-text-muted space-y-1">
              <p><span class="text-text-secondary font-medium">全文</span> — 使用 MinerU 从 PDF 提取的完整 Markdown 正文，信息最全但 Token 消耗较高</p>
              <p><span class="text-text-secondary font-medium">原文摘要</span> — 仅使用论文原始摘要，Token 消耗最低，适合快速概览对比</p>
              <p><span class="text-text-secondary font-medium">系统总结</span> — 使用系统生成的中文结构化摘要，信息量适中（默认）</p>
            </div>
          </div>
        </fieldset>

        <!-- Generation Parameters section -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
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
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors"
              />
              <button
                v-if="hasDefault('temperature')"
                :disabled="isDefault('temperature')"
                class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                :class="isDefault('temperature')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                @click="resetField('temperature')"
              >恢复默认</button>
            </div>
            <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.temperature }}</p>
          </div>

          <!-- Max Tokens -->
          <div>
            <label class="block text-xs font-medium text-text-secondary mb-1.5">Max Tokens</label>
            <div class="flex items-center gap-2">
              <input
                v-model.number="form.max_tokens"
                type="number"
                step="256"
                min="256"
                max="32768"
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors"
              />
              <button
                v-if="hasDefault('max_tokens')"
                :disabled="isDefault('max_tokens')"
                class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                :class="isDefault('max_tokens')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                @click="resetField('max_tokens')"
              >恢复默认</button>
            </div>
            <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.max_tokens }}</p>
          </div>
        </fieldset>

        <!-- Token Budget section -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
          <legend class="px-2 text-xs font-semibold text-text-secondary">输入 Token 预算</legend>

          <!-- Input Hard Limit -->
          <div class="mb-5">
            <label class="block text-xs font-medium text-text-secondary mb-1.5">输入硬上限 (Input Hard Limit)</label>
            <div class="flex items-center gap-2">
              <input
                v-model.number="form.input_hard_limit"
                type="number"
                step="1024"
                min="1024"
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors"
              />
              <button
                v-if="hasDefault('input_hard_limit')"
                :disabled="isDefault('input_hard_limit')"
                class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                :class="isDefault('input_hard_limit')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                @click="resetField('input_hard_limit')"
              >恢复默认</button>
            </div>
            <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.input_hard_limit }}. 模型上下文窗口的硬上限。</p>
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
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#8b5cf6] transition-colors"
              />
              <button
                v-if="hasDefault('input_safety_margin')"
                :disabled="isDefault('input_safety_margin')"
                class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                :class="isDefault('input_safety_margin')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                @click="resetField('input_safety_margin')"
              >恢复默认</button>
            </div>
            <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.input_safety_margin }}. 留给输出的预留空间。</p>
          </div>
        </fieldset>

        <!-- System Prompt section -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
          <legend class="px-2 text-xs font-semibold text-text-secondary">System Prompt</legend>

          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-xs font-medium text-text-secondary">对比分析系统提示词</label>
              <button
                v-if="hasDefault('system_prompt')"
                :disabled="isDefault('system_prompt')"
                class="shrink-0 px-3 py-1 rounded-lg text-xs border transition-colors"
                :class="isDefault('system_prompt')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#8b5cf6]/30 text-[#8b5cf6] bg-[#8b5cf6]/10 hover:bg-[#8b5cf6]/20 cursor-pointer'"
                @click="resetField('system_prompt')"
              >恢复默认</button>
            </div>
            <textarea
              v-model="form.system_prompt"
              rows="12"
              class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#8b5cf6] transition-colors resize-y leading-relaxed font-mono"
              placeholder="输入系统提示词..."
            ></textarea>
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
              ? 'bg-[#8b5cf6]/50 text-white/50 cursor-not-allowed'
              : 'bg-gradient-to-r from-[#6366f1] to-[#8b5cf6] text-white hover:opacity-90 shadow-lg shadow-[#8b5cf6]/20'"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? '保存中...' : '保存设置' }}
          </button>
        </div>
      </div>

      <!-- Inspiration settings form -->
      <div v-else-if="activeNav === 'inspiration'" class="max-w-2xl mx-auto px-8 py-8">
        <!-- Section title -->
        <div class="mb-8">
          <h2 class="text-lg font-bold text-text-primary flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-5 h-5 text-[#f59e0b]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 18h6" /><path d="M10 22h4" /><path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
            </svg>
            灵感涌现设置
          </h2>
          <p class="text-xs text-text-muted mt-1">配置灵感涌现分析所使用的大语言模型参数</p>
        </div>

        <!-- LLM Connection status banner -->
        <div
          class="mb-6 px-4 py-3 rounded-lg border text-sm flex items-center gap-2"
          :class="isLlmConfigured
            ? 'bg-tinder-green/10 border-tinder-green/30 text-tinder-green'
            : 'bg-tinder-pink/10 border-tinder-pink/30 text-tinder-pink'"
        >
          <svg v-if="isLlmConfigured" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" /><polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <span>
            {{ isLlmConfigured ? 'LLM 已配置，灵感涌现功能可用' : 'LLM 未配置，请填写以下连接信息以启用灵感涌现' }}
          </span>
        </div>

        <!-- LLM Connection section -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
          <legend class="px-2 text-xs font-semibold text-text-secondary">LLM 连接配置</legend>

          <!-- LLM Base URL -->
          <div class="mb-5">
            <label class="block text-xs font-medium text-text-secondary mb-1.5">API URL</label>
            <div class="flex items-center gap-2">
              <input
                v-model="form.llm_base_url"
                type="text"
                placeholder="例如: https://api.openai.com/v1"
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#f59e0b] transition-colors"
              />
            </div>
          </div>

          <!-- LLM API Key -->
          <div class="mb-5">
            <label class="block text-xs font-medium text-text-secondary mb-1.5">API Key</label>
            <div class="flex items-center gap-2">
              <div class="flex-1 relative">
                <input
                  v-model="form.llm_api_key"
                  :type="showApiKey ? 'text' : 'password'"
                  placeholder="sk-..."
                  class="w-full px-3 py-2 pr-10 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#f59e0b] transition-colors font-mono"
                />
                <button
                  type="button"
                  class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-text-muted hover:text-text-secondary transition-colors"
                  @click="showApiKey = !showApiKey"
                  :title="showApiKey ? '隐藏' : '显示'"
                >
                  <svg v-if="showApiKey" xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
                  </svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" /><line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <!-- LLM Model -->
          <div>
            <label class="block text-xs font-medium text-text-secondary mb-1.5">Model</label>
            <div class="flex items-center gap-2">
              <input
                v-model="form.llm_model"
                type="text"
                placeholder="例如: gpt-4o, claude-sonnet-4-20250514, qwen-plus"
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#f59e0b] transition-colors"
              />
            </div>
          </div>
        </fieldset>

        <!-- Data Source info (fixed) -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
          <legend class="px-2 text-xs font-semibold text-text-secondary">数据源</legend>
          <div class="flex items-center gap-2 text-sm text-text-secondary">
            <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4 text-[#f59e0b]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            <span>数据源固定为<span class="text-text-primary font-medium">选中的灵感涌现条目内容</span>，无需额外配置。</span>
          </div>
        </fieldset>

        <!-- Generation Parameters section -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
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
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#f59e0b] transition-colors"
              />
              <button
                v-if="hasDefault('temperature')"
                :disabled="isDefault('temperature')"
                class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                :class="isDefault('temperature')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#f59e0b]/30 text-[#f59e0b] bg-[#f59e0b]/10 hover:bg-[#f59e0b]/20 cursor-pointer'"
                @click="resetField('temperature')"
              >恢复默认</button>
            </div>
            <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.temperature }}</p>
          </div>

          <!-- Max Tokens -->
          <div>
            <label class="block text-xs font-medium text-text-secondary mb-1.5">Max Tokens</label>
            <div class="flex items-center gap-2">
              <input
                v-model.number="form.max_tokens"
                type="number"
                step="256"
                min="256"
                max="32768"
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#f59e0b] transition-colors"
              />
              <button
                v-if="hasDefault('max_tokens')"
                :disabled="isDefault('max_tokens')"
                class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                :class="isDefault('max_tokens')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#f59e0b]/30 text-[#f59e0b] bg-[#f59e0b]/10 hover:bg-[#f59e0b]/20 cursor-pointer'"
                @click="resetField('max_tokens')"
              >恢复默认</button>
            </div>
            <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.max_tokens }}</p>
          </div>
        </fieldset>

        <!-- Token Budget section -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
          <legend class="px-2 text-xs font-semibold text-text-secondary">输入 Token 预算</legend>

          <!-- Input Hard Limit -->
          <div class="mb-5">
            <label class="block text-xs font-medium text-text-secondary mb-1.5">输入硬上限 (Input Hard Limit)</label>
            <div class="flex items-center gap-2">
              <input
                v-model.number="form.input_hard_limit"
                type="number"
                step="1024"
                min="1024"
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#f59e0b] transition-colors"
              />
              <button
                v-if="hasDefault('input_hard_limit')"
                :disabled="isDefault('input_hard_limit')"
                class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                :class="isDefault('input_hard_limit')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#f59e0b]/30 text-[#f59e0b] bg-[#f59e0b]/10 hover:bg-[#f59e0b]/20 cursor-pointer'"
                @click="resetField('input_hard_limit')"
              >恢复默认</button>
            </div>
            <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.input_hard_limit }}. 模型上下文窗口的硬上限。</p>
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
                class="flex-1 px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary focus:outline-none focus:border-[#f59e0b] transition-colors"
              />
              <button
                v-if="hasDefault('input_safety_margin')"
                :disabled="isDefault('input_safety_margin')"
                class="shrink-0 px-3 py-2 rounded-lg text-xs border transition-colors"
                :class="isDefault('input_safety_margin')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#f59e0b]/30 text-[#f59e0b] bg-[#f59e0b]/10 hover:bg-[#f59e0b]/20 cursor-pointer'"
                @click="resetField('input_safety_margin')"
              >恢复默认</button>
            </div>
            <p class="text-[11px] text-text-muted mt-1">默认值: {{ defaults.input_safety_margin }}. 留给输出的预留空间。</p>
          </div>
        </fieldset>

        <!-- System Prompt section -->
        <fieldset class="mb-8 border border-border rounded-lg p-5">
          <legend class="px-2 text-xs font-semibold text-text-secondary">System Prompt</legend>

          <div>
            <div class="flex items-center justify-between mb-1.5">
              <label class="text-xs font-medium text-text-secondary">灵感涌现系统提示词</label>
              <button
                v-if="hasDefault('system_prompt')"
                :disabled="isDefault('system_prompt')"
                class="shrink-0 px-3 py-1 rounded-lg text-xs border transition-colors"
                :class="isDefault('system_prompt')
                  ? 'border-border text-text-muted bg-transparent cursor-not-allowed'
                  : 'border-[#f59e0b]/30 text-[#f59e0b] bg-[#f59e0b]/10 hover:bg-[#f59e0b]/20 cursor-pointer'"
                @click="resetField('system_prompt')"
              >恢复默认</button>
            </div>
            <textarea
              v-model="form.system_prompt"
              rows="12"
              class="w-full px-3 py-2 bg-bg-elevated border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-[#f59e0b] transition-colors resize-y leading-relaxed font-mono"
              placeholder="输入系统提示词..."
            ></textarea>
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
              ? 'bg-[#f59e0b]/50 text-white/50 cursor-not-allowed'
              : 'bg-gradient-to-r from-[#f59e0b] to-[#f97316] text-white hover:opacity-90 shadow-lg shadow-[#f59e0b]/20'"
            :disabled="saving"
            @click="handleSave"
          >
            {{ saving ? '保存中...' : '保存设置' }}
          </button>
        </div>
      </div>

      <!-- Placeholder for disabled features -->
      <div v-else class="flex items-center justify-center h-full">
        <div class="text-center">
          <div class="text-5xl mb-4 opacity-30">
            <span v-if="activeNav === 'paper_summary'">📄</span>
            <span v-else-if="activeNav === 'theme_filter'">🔍</span>
            <span v-else>⚙️</span>
          </div>
          <h3 class="text-sm font-semibold text-text-muted mb-1">{{ navItems.find(i => i.key === activeNav)?.label }}</h3>
          <p class="text-xs text-text-muted">此功能即将推出，敬请期待</p>
        </div>
      </div>
    </div>
  </div>
</template>
