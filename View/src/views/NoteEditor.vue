<script setup lang="ts">
import { ref, watch, onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import { fetchNoteDetail, updateNote } from '../api'
import type { KbNote } from '../types/paper'

const props = defineProps<{
  id: string
  embedded?: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const router = useRouter()

const note = ref<KbNote | null>(null)
const loading = ref(true)
const saving = ref(false)
const title = ref('')
const lastSavedAt = ref('')
const titleManuallyEdited = ref(false)

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

  // Try first heading
  const heading = json.content.find((n: any) => n.type === 'heading')
  if (heading) {
    const text = getTextFromNode(heading).trim()
    if (text) return text
  }

  // Fallback: first 10 chars of plain text
  const plain = editor.value.getText().trim()
  if (plain) return plain.slice(0, 10)

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

function goBack() {
  // flush pending save
  if (saveTimer) {
    clearTimeout(saveTimer)
    doSave()
  }
  if (props.embedded) {
    emit('close')
  } else {
    router.back()
  }
}

async function saveAndClose() {
  if (saveTimer) clearTimeout(saveTimer)
  await doSave()
  goBack()
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
