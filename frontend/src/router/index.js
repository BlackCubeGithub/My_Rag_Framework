import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Chat',
    component: () => import('../views/RAGChat.vue'),
  },
  {
    path: '/documents',
    name: 'Documents',
    component: () => import('../views/DocManage.vue'),
  },
  {
    path: '/traces',
    name: 'Traces',
    component: () => import('../views/TraceDebug.vue'),
  },
  {
    path: '/metrics',
    name: 'Metrics',
    component: () => import('../views/MetricsPanel.vue'),
  },
  {
    path: '/debug',
    name: 'Debug',
    component: () => import('../views/DebugTool.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
