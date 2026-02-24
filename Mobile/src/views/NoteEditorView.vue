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

defineOptions({ name: 'NoteEditorView' })

const props = defineProps<{
  id: string
}>()

const router = useRouter()

const note = ref<KbNote | null>(null)
const loading = ref(true)
const saving = ref(false)
const title = ref('')
const lastSavedAt = ref('')
const titleManuallyEdited = ref(false)

const leaveMode = ref<'normal' | 'explicit-save' | null>(null)

let saveTimer: ReturnType<typeof setTimeout> | null = null

function getTextFromNode(node: any): string {
  if (node.text) return node.text
  if (node.content) return node.content.map(getTextFromNode).join('')
  return ''
}

function extractDefaultTitle(): string {
  if (!editor.value) return ''
  const json = editor.value.getJSON()
  if (!json.content || json.content.length === 0) return ''

  const heading = json.content.find((n: any) => n.type === 'heading')
  if (heading) {
    const text = getTextFromNode(heading).trim()
    if (text) return text
  }

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

function isEffectivelyEmpty(): boolean {
  if (!editor.value) return true
  const json = editor.value.getJSON()
  const t = title.value.trim()
  const isDefaultTitle = (v: string) => v === '' || v === '未命名笔记' || v === '无标题笔记' || v === '新建笔记'

  if (!json.content || json.content.length === 0) {
    return isDefaultTitle(t)
  }

  const text = json.content.map((n: any) => getTextFromNode(n)).join('').trim()

  if (!text) return isDefaultTitle(t)

  return false
}

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

async function goBack() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  leaveMode.value = 'normal'
  router.back()
}

async function saveAndClose() {
  if (saveTimer) clearTimeout(saveTimer)
  leaveMode.value = 'explicit-save'
  await doSave()
  router.back()
}

function toggleBold() { editor.value?.chain().focus().toggleBold().run() }
function toggleItalic() { editor.value?.chain().focus().toggleItalic().run() }
function toggleH1() { editor.value?.chain().focus().toggleHeading({ level: 1 }).run() }
function toggleH2() { editor.value?.chain().focus().toggleHeading({ level: 2 }).run() }
function toggleBulletList() { editor.value?.chain().focus().toggleBulletList().run() }
function toggleOrderedList() { editor.value?.chain().focus().toggleOrderedList().run() }
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

onBeforeRouteLeave(async (_to, _from, next) => {
  if (!note.value) {
    next()
    return
  }

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
</script>

<template>
  <div class="h-full flex flex-col bg-bg">
    <!-- Top bar -->
    <div class="shrink-0 safe-area-top">
      <div class="flex items-center gap-3 px-4 py-3 border-b border-border bg-bg-sidebar">
        <button
          class="w-9 h-9 rounded-lg flex items-center justify-center bg-bg-elevated active:bg-bg-hover text-text-secondary border-none"
          @click="goBack"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>

        <input
          v-model="title"
          @input="onTitleInput"
          class="flex-1 bg-transparent border-none text-base font-semibold text-text-primary focus:outline-none placeholder:text-text-muted"
          placeholder="笔记标题..."
        />

        <span v-if="saving" class="text-xs text-text-muted">保存中...</span>
        <span v-else-if="lastSavedAt" class="text-xs text-text-muted">{{ lastSavedAt }}</span>

        <button
          class="px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-gradient-to-r from-[#fd267a] to-[#ff6036] border-none active:opacity-90"
          @click="saveAndClose"
        >保存</button>
      </div>

      <!-- Toolbar -->
      <div class="flex items-center gap-0.5 px-4 py-2 border-b border-border bg-bg-sidebar overflow-x-auto no-scrollbar">
        <button class="toolbar-btn" :class="{ active: editor?.isActive('heading', { level: 1 }) }" @click="toggleH1">H1</button>
        <button class="toolbar-btn" :class="{ active: editor?.isActive('heading', { level: 2 }) }" @click="toggleH2">H2</button>
        <div class="toolbar-divider"></div>
        <button class="toolbar-btn" :class="{ active: editor?.isActive('bold') }" @click="toggleBold"><strong>B</strong></button>
        <button class="toolbar-btn" :class="{ active: editor?.isActive('italic') }" @click="toggleItalic"><em>I</em></button>
        <div class="toolbar-divider"></div>
        <button class="toolbar-btn" :class="{ active: editor?.isActive('bulletList') }" @click="toggleBulletList">•</button>
        <button class="toolbar-btn" :class="{ active: editor?.isActive('orderedList') }" @click="toggleOrderedList">1.</button>
        <div class="toolbar-divider"></div>
        <button class="toolbar-btn" @click="doUndo">↶</button>
        <button class="toolbar-btn" @click="doRedo">↷</button>
      </div>
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" class="flex-1 flex items-center justify-center text-text-muted">加载中...</div>
    <div v-else-if="!note" class="flex-1 flex items-center justify-center text-text-muted">笔记不存在</div>

    <!-- Editor -->
    <div v-else class="flex-1 overflow-y-auto">
      <div class="max-w-3xl mx-auto px-4 py-6">
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
  width: 36px;
  height: 36px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  transition: all 0.15s;
}
.toolbar-btn:active {
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

.no-scrollbar::-webkit-scrollbar { display: none; }
.no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

:deep(.note-editor-content) {
  outline: none;
  min-height: 300px;
}

:deep(.note-editor-content p) {
  margin: 0.75rem 0;
  line-height: 1.6;
}

:deep(.note-editor-content h1) {
  font-size: 1.5rem;
  font-weight: bold;
  margin: 1rem 0 0.5rem;
}

:deep(.note-editor-content h2) {
  font-size: 1.25rem;
  font-weight: bold;
  margin: 0.875rem 0 0.5rem;
}

:deep(.note-editor-content ul),
:deep(.note-editor-content ol) {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

:deep(.note-editor-content li) {
  margin: 0.25rem 0;
}

:deep(.note-editor-content a) {
  color: var(--color-tinder-pink);
  text-decoration: underline;
}

:deep(.note-editor-content img) {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 1rem 0;
}

:deep(.ProseMirror-focused) {
  outline: none;
}
</style>
