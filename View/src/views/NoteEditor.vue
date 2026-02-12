<script setup lang="ts">
import { ref, watch, onBeforeUnmount, onMounted } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import { fetchNoteDetail, updateNote, deleteNote as deleteNoteApi } from '../api'
import type { KbNote } from '../types/paper'

const props = defineProps<{
  id: string
  embedded?: boolean
}>()

const emit = defineEmits<{
  close: []
  saved: [{ id: number; title: string }]
}>()

const router = useRouter()

const note = ref<KbNote | null>(null)
const loading = ref(true)
const saving = ref(false)
const title = ref('')
const lastSavedAt = ref('')
const titleManuallyEdited = ref(false)

// 离开路由的方式标记（仅路由模式下使用）
const leaveMode = ref<'normal' | 'explicit-save' | null>(null)

let saveTimer: ReturnType<typeof setTimeout> | null = null

// ---- Auto title helpers ----
function getTextFromNode(node: any): string {
  if (node.text) return node.text
  if (node.content) return node.content.map(getTextFromNode).join('')
  return ''
}

function extractDefaultTitle(): string {
  if (!editor.value) return ''
  const json = editor.value.getJSON()
  if (!json.content || json.content.length === 0) return ''

  // 优先取第一个 heading 作为默认标题
  const heading = json.content.find((n: any) => n.type === 'heading')
  if (heading) {
    const text = getTextFromNode(heading).trim()
    if (text) return text
  }

  // 若没有标题块，则退化为“第一段文本”的前若干字符
  const firstBlock = json.content.find((n: any) => n.type === 'paragraph' || n.type === 'heading') || json.content[0]
  if (firstBlock) {
    const text = getTextFromNode(firstBlock).trim()
    if (text) return text.slice(0, 60)
  }

  return ''
}

function syncAutoTitle() {
  if (titleManuallyEdited.value) return
  const auto = extractDefaultTitle()
  if (auto) title.value = auto
}

const editor = useEditor({
  extensions: [
    StarterKit.configure({
      codeBlock: false,
    }),
    Image.configure({ inline: false, allowBase64: true }),
    Link.configure({ openOnClick: true, autolink: true }),
    Placeholder.configure({ placeholder: '开始写笔记...' }),
  ],
  editorProps: {
    attributes: {
      class: 'note-editor-content',
    },
  },
  onUpdate() {
    syncAutoTitle()
    scheduleSave()
  },
})

// 判断当前笔记是否“空”（无标题且正文无内容）
function isEffectivelyEmpty(): boolean {
  if (!editor.value) return true
  const json = editor.value.getJSON()
  const t = title.value.trim()
  const isDefaultTitle = (v: string) => v === '' || v === '未命名笔记' || v === '无标题笔记' || v === '新建笔记'

  if (!json.content || json.content.length === 0) {
    // 没有任何正文内容时，仅将“默认标题”视为空
    return isDefaultTitle(t)
  }

  const text = json.content.map((n: any) => getTextFromNode(n)).join('').trim()

  // 无正文 + 默认标题 -> 空笔记；否则视为非空
  if (!text) return isDefaultTitle(t)

  return false
}

// 供父组件调用：立即执行一次保存（如果有笔记可保存）
async function flushSave() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  await doSave()
}

async function loadNote() {
  loading.value = true
  titleManuallyEdited.value = false
  try {
    const data = await fetchNoteDetail(Number(props.id))
    note.value = data
    title.value = data.title
    if (editor.value && data.content) {
      editor.value.commands.setContent(data.content)
    }
    // If the loaded title looks like a default (empty or "无标题笔记"), keep auto-title active
    const t = data.title.trim()
    if (t && t !== '无标题笔记' && t !== '新建笔记') {
      titleManuallyEdited.value = true
    }
  } catch {
    note.value = null
  } finally {
    loading.value = false
  }
}

function scheduleSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => doSave(), 2000)
}

async function doSave() {
  if (!note.value || !editor.value) return
  saving.value = true
  try {
    const html = editor.value.getHTML()
    await updateNote(note.value.id, { title: title.value, content: html })
    lastSavedAt.value = new Date().toLocaleTimeString()
    // 通知父组件：已保存，携带最新标题
    emit('saved', { id: note.value.id, title: title.value })
  } catch {
    // silent
  } finally {
    saving.value = false
  }
}

function onTitleInput() {
  titleManuallyEdited.value = true
  scheduleSave()
}

async function goBack() {
  if (props.embedded) {
    // 内嵌模式：仍然保持“始终保存再关闭”的旧行为，由父组件决定是否删除
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    await doSave()
    emit('close')
    return
  }

  // 路由模式：交由 onBeforeRouteLeave 按“空则删，有则保存”规则处理
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  leaveMode.value = 'normal'
  router.back()
}

async function saveAndClose() {
  if (props.embedded) {
    if (saveTimer) clearTimeout(saveTimer)
    await doSave()
    emit('close')
    return
  }

  // 路由模式下显式保存：无论是否为空都保留该笔记
  if (saveTimer) clearTimeout(saveTimer)
  leaveMode.value = 'explicit-save'
  await doSave()
  router.back()
}

// Toolbar helpers
function toggleBold() { editor.value?.chain().focus().toggleBold().run() }
function toggleItalic() { editor.value?.chain().focus().toggleItalic().run() }
function toggleStrike() { editor.value?.chain().focus().toggleStrike().run() }
function toggleH1() { editor.value?.chain().focus().toggleHeading({ level: 1 }).run() }
function toggleH2() { editor.value?.chain().focus().toggleHeading({ level: 2 }).run() }
function toggleH3() { editor.value?.chain().focus().toggleHeading({ level: 3 }).run() }
function toggleBulletList() { editor.value?.chain().focus().toggleBulletList().run() }
function toggleOrderedList() { editor.value?.chain().focus().toggleOrderedList().run() }
function toggleBlockquote() { editor.value?.chain().focus().toggleBlockquote().run() }
function toggleCodeBlock() { editor.value?.chain().focus().toggleCodeBlock().run() }
function addImage() {
  const url = window.prompt('输入图片 URL')
  if (url) editor.value?.chain().focus().setImage({ src: url }).run()
}
function addLink() {
  const url = window.prompt('输入链接 URL')
  if (url) editor.value?.chain().focus().setLink({ href: url }).run()
}
function doUndo() { editor.value?.chain().focus().undo().run() }
function doRedo() { editor.value?.chain().focus().redo().run() }

onMounted(loadNote)

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    doSave()
  }
  editor.value?.destroy()
})

watch(() => props.id, loadNote)

// 路由离开守卫：仅在非 embedded 模式下应用“空则删，有则自动保存”规则
onBeforeRouteLeave(async (_to, _from, next) => {
  if (props.embedded || !note.value) {
    next()
    return
  }

  // 显式点击“保存”离开时，已保存过，直接放行
  if (leaveMode.value === 'explicit-save') {
    leaveMode.value = null
    next()
    return
  }

  const empty = isEffectivelyEmpty()
  try {
    if (empty) {
      await deleteNoteApi(note.value.id)
    } else {
      await flushSave()
    }
  } catch {
    // 失败不阻塞导航
  } finally {
    leaveMode.value = null
  }
  next()
})

// 向父组件暴露方法，用于判断是否为空 & 强制保存
defineExpose({
  isEffectivelyEmpty,
  flushSave,
})
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Top bar -->
    <div class="flex items-center gap-3 px-4 py-3 border-b border-border bg-bg-sidebar shrink-0">
      <button
        class="w-8 h-8 rounded-lg flex items-center justify-center bg-bg-elevated hover:bg-bg-hover text-text-secondary hover:text-text-primary border-none cursor-pointer transition-colors text-sm"
        @click="goBack"
        title="返回"
      >&larr;</button>

      <input
        v-model="title"
        @input="onTitleInput"
        class="flex-1 bg-transparent border-none text-lg font-semibold text-text-primary focus:outline-none placeholder-text-muted"
        placeholder="笔记标题..."
      />

      <span v-if="saving" class="text-xs text-text-muted">保存中...</span>
      <span v-else-if="lastSavedAt" class="text-xs text-text-muted">已保存 {{ lastSavedAt }}</span>

      <button
        class="px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-gradient-to-r from-[#fd267a] to-[#ff6036] border-none cursor-pointer hover:opacity-90 transition-opacity"
        @click="saveAndClose"
      >保存</button>
    </div>

    <!-- Toolbar -->
    <div class="flex items-center gap-0.5 px-4 py-2 border-b border-border bg-bg-sidebar shrink-0 overflow-x-auto">
      <button class="toolbar-btn" :class="{ active: editor?.isActive('heading', { level: 1 }) }" @click="toggleH1" title="标题 1">H1</button>
      <button class="toolbar-btn" :class="{ active: editor?.isActive('heading', { level: 2 }) }" @click="toggleH2" title="标题 2">H2</button>
      <button class="toolbar-btn" :class="{ active: editor?.isActive('heading', { level: 3 }) }" @click="toggleH3" title="标题 3">H3</button>
      <div class="toolbar-divider"></div>
      <button class="toolbar-btn" :class="{ active: editor?.isActive('bold') }" @click="toggleBold" title="粗体"><strong>B</strong></button>
      <button class="toolbar-btn" :class="{ active: editor?.isActive('italic') }" @click="toggleItalic" title="斜体"><em>I</em></button>
      <button class="toolbar-btn" :class="{ active: editor?.isActive('strike') }" @click="toggleStrike" title="删除线"><s>S</s></button>
      <div class="toolbar-divider"></div>
      <button class="toolbar-btn" :class="{ active: editor?.isActive('bulletList') }" @click="toggleBulletList" title="无序列表">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><circle cx="5" cy="6" r="1.5" fill="currentColor"/><circle cx="5" cy="12" r="1.5" fill="currentColor"/><circle cx="5" cy="18" r="1.5" fill="currentColor"/></svg>
      </button>
      <button class="toolbar-btn" :class="{ active: editor?.isActive('orderedList') }" @click="toggleOrderedList" title="有序列表">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="10" y1="6" x2="20" y2="6"/><line x1="10" y1="12" x2="20" y2="12"/><line x1="10" y1="18" x2="20" y2="18"/><text x="3" y="8" font-size="8" fill="currentColor" stroke="none">1</text><text x="3" y="14" font-size="8" fill="currentColor" stroke="none">2</text><text x="3" y="20" font-size="8" fill="currentColor" stroke="none">3</text></svg>
      </button>
      <button class="toolbar-btn" :class="{ active: editor?.isActive('blockquote') }" @click="toggleBlockquote" title="引用">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M3 12h18M3 18h18" opacity="0.4"/><line x1="3" y1="6" x2="3" y2="18" stroke-width="3"/></svg>
      </button>
      <button class="toolbar-btn" :class="{ active: editor?.isActive('codeBlock') }" @click="toggleCodeBlock" title="代码块">&lt;/&gt;</button>
      <div class="toolbar-divider"></div>
      <button class="toolbar-btn" @click="addImage" title="插入图片">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>
      </button>
      <button class="toolbar-btn" @click="addLink" title="插入链接">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
      </button>
      <div class="toolbar-divider"></div>
      <button class="toolbar-btn" @click="doUndo" title="撤销">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/></svg>
      </button>
      <button class="toolbar-btn" @click="doRedo" title="重做">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3L21 13"/></svg>
      </button>
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" class="flex-1 flex items-center justify-center text-text-muted">加载中...</div>
    <div v-else-if="!note" class="flex-1 flex items-center justify-center text-text-muted">笔记不存在</div>

    <!-- Editor -->
    <div v-else class="flex-1 overflow-y-auto">
      <div class="max-w-3xl mx-auto px-6 py-8">
        <EditorContent :editor="editor" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s;
}
.toolbar-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}
.toolbar-btn.active {
  background: var(--color-bg-elevated);
  color: var(--color-tinder-pink);
}
.toolbar-divider {
  width: 1px;
  height: 20px;
  background: var(--color-border);
  margin: 0 4px;
}
</style>
