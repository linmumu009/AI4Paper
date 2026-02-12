import { createRouter, createWebHistory } from 'vue-router'
import { ensureAuthInitialized, isAdmin, isAuthenticated } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
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
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('../views/AdminUsers.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
  ],
})

router.beforeEach(async (to) => {
  await ensureAuthInitialized()
  if (!to.meta.requiresAuth) return true
  if (isAuthenticated.value) return true
  return {
    path: '/login',
    query: { redirect: to.fullPath },
  }
})

router.beforeEach(async (to) => {
  if (!to.meta.requiresAdmin) return true
  if (isAdmin.value) return true
  return { path: '/' }
})

export default router
