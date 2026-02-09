import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'digest',
      component: () => import('../views/DailyDigest.vue'),
    },
    {
      path: '/papers',
      name: 'papers',
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
    },
  ],
})

export default router
