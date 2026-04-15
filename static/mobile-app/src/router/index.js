import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory('/m/'),
  routes: [
    {
      path: '/',
      redirect: '/project'
    },
    {
      path: '/project',
      name: 'ProjectDetail',
      component: () => import('@/views/ProjectDetail.vue')
    }
  ]
})

export default router
