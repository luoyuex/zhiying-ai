import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/LoginPage.vue'),
      meta: { guestOnly: true, title: '登录' },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/pages/RegisterPage.vue'),
      meta: { guestOnly: true, title: '注册' },
    },
    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: () => import('@/pages/ForgotPasswordPage.vue'),
      meta: { guestOnly: true, title: '重置密码' },
    },
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/pages/DashboardPage.vue'),
      meta: { requiresAuth: true, title: '首页' },
    },
    {
      path: '/screener',
      name: 'screener',
      component: () => import('@/pages/ScreenerPage.vue'),
      meta: { requiresAuth: true, title: '选股' },
    },
    {
      path: '/watchlist',
      name: 'watchlist',
      component: () => import('@/pages/WatchlistPage.vue'),
      meta: { requiresAuth: true, title: '自选股' },
    },
    {
      path: '/stock/:symbol',
      name: 'stock',
      component: () => import('@/pages/StockDetailPage.vue'),
      meta: { requiresAuth: true, title: '个股行情' },
    },
    {
      path: '/reports',
      name: 'reports',
      component: () => import('@/pages/ReportsPage.vue'),
      meta: { requiresAuth: true, title: '历史报告' },
    },
    {
      path: '/reports/compare',
      name: 'report-compare',
      component: () => import('@/pages/ReportComparePage.vue'),
      meta: { requiresAuth: true, title: '报告对比' },
    },
    {
      path: '/reports/:id',
      name: 'report',
      component: () => import('@/pages/ReportDetailPage.vue'),
      meta: { requiresAuth: true, title: '分析报告' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.bootstrap()

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return {
      name: 'login',
      query: to.fullPath === '/' ? {} : { redirect: to.fullPath },
    }
  }

  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { name: 'dashboard' }
  }

  return true
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : ''
  document.title = title ? `${title} · 智盈 AI` : '智盈 AI · A 股 AI 分析工作台'
})

export default router
