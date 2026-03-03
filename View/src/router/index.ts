import { createRouter, createWebHistory, createWebHashHistory } from 'vue-router'
import { ensureAuthInitialized, isAdmin, isAuthenticated } from '../stores/auth'

// In Tauri the frontend is served from a custom protocol (tauri://localhost).
// WebHashHistory avoids 404s on hard refresh and works without a server-side
// SPA fallback.  In regular browser mode keep WebHistory for clean URLs.
const isTauri = typeof import.meta.env.VITE_API_BASE === 'string'
  && import.meta.env.VITE_API_BASE !== ''

const router = createRouter({
  history: isTauri ? createWebHashHistory() : createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'digest',
      component: () => import('../views/DailyDigest.vue'),
    },
    {
      path: '/inspiration',
      name: 'inspiration',
      component: () => import('../views/PaperList.vue'),
    },
    // ---------------------------------------------------------------------------
    // Idea Generation v2 routes (灵感生成)
    // ---------------------------------------------------------------------------
    {
      path: '/workbench',
      name: 'workbench',
      component: () => import('../views/WorkbenchView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/idea',
      redirect: '/workbench',
    },
    {
      path: '/idea/candidates/:id',
      name: 'idea-detail',
      component: () => import('../views/IdeaDetailView.vue'),
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/idea/atoms',
      name: 'idea-atoms',
      component: () => import('../views/AtomBrowser.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/idea/exemplars',
      name: 'idea-exemplars',
      component: () => import('../views/ExemplarView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/idea/eval',
      name: 'idea-eval',
      component: () => import('../views/EvalReplayView.vue'),
      meta: { requiresAuth: true },
    },
    // ---------------------------------------------------------------------------
    {
      path: '/papers/:id',
      name: 'paper-detail',
      component: () => import('../views/PaperDetail.vue'),
      props: true,
    },
    {
      path: '/notes/:id',
      name: 'note-editor',
      component: () => import('../views/NoteEditor.vue'),
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/Login.vue'),
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/Register.vue'),
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('../views/ProfileSettings.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin',
      redirect: '/admin/users',
    },
    {
      path: '/admin/user',
      redirect: '/admin/users',
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('../views/AdminUsers.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
  ],
})

router.beforeEach(async (to) => {
  // 确保认证状态已初始化
  await ensureAuthInitialized()
  
  // 检查是否需要管理员权限
  if (to.meta.requiresAdmin) {
    // 先检查是否已登录
    if (!isAuthenticated.value) {
      return {
        path: '/login',
        query: { redirect: to.fullPath },
      }
    }
    // 再检查是否有管理员权限
    if (!isAdmin.value) {
      return { path: '/' }
    }
  }
  
  // 检查是否需要登录
  if (to.meta.requiresAuth) {
    if (!isAuthenticated.value) {
      return {
        path: '/login',
        query: { redirect: to.fullPath },
      }
    }
  }
  
  return true
})

export default router
