import { createRouter, createWebHashHistory } from 'vue-router'
import { getWorkspace } from '@/api/url'

// hash 路由的 base 跟随当前工作空间：/m/w/<slug>/
// 没有 workspace 时回退 /m/，由后端把用户重定向到 picker
const slug = getWorkspace()
const base = slug ? `/m/w/${slug}/` : '/m/'

const router = createRouter({
  history: createWebHashHistory(base),
  routes: [
    {
      path: '/',
      redirect: '/project'
    },
    {
      path: '/project',
      name: 'ProjectDetail',
      component: () => import('@/views/ProjectDetail.vue')
    },
    {
      path: '/settings',
      name: 'Settings',
      component: () => import('@/views/Settings.vue')
    }
  ]
})

export default router
