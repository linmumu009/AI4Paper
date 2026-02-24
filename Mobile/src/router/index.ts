import { createRouter, createWebHistory } from 'vue-router'
import { ensureAuthInitialized, isAuthenticated, isAdmin } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/recommend',
    },
    {
      path: '/recommend',
      name: 'recommend',
      component: () => import('../views/RecommendView.vue'),
      meta: { tab: 'recommend' },
    },
    {
      path: '/idea',
      name: 'idea',
      component: () => import('../views/IdeaView.vue'),
      meta: { tab: 'idea', requiresAuth: true },
    },
    {
      path: '/idea/candidates/:id',
      name: 'idea-detail',
      component: () => import('../views/IdeaDetailView.vue'),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('../views/KnowledgeView.vue'),
      meta: { tab: 'knowledge', requiresAuth: true },
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('../views/ProfileView.vue'),
      meta: { tab: 'profile' },
    },
    {
      path: '/paper/:id',
      name: 'paper-detail',
      component: () => import('../views/PaperDetailView.vue'),
      props: true,
    },
    {
      path: '/compare',
      name: 'compare',
      component: () => import('../views/CompareView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/compare-result/:id',
      name: 'compare-result',
      component: () => import('../views/CompareResultView.vue'),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: '/settings/idea-generate',
      name: 'idea-generate-settings',
      component: () => import('../views/IdeaGenerateSettingsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin/recommend-config',
      name: 'admin-recommend-config',
      component: () => import('../views/AdminRecommendConfigView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/admin/idea-system-config',
      name: 'admin-idea-system-config',
      component: () => import('../views/AdminIdeaSystemConfigView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  await ensureAuthInitialized()
  if (!to.meta.requiresAuth) return true
  if (!isAuthenticated.value) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresAdmin && !isAdmin.value) {
    return { path: '/profile' }
  }
  return true
})

export default router
