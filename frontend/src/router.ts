import { createRouter, createWebHashHistory } from 'vue-router';
import AdvisorView from './views/AdvisorView.vue';

// LoginView / LoginWaitView 保留在 views/，等 MIS 后端就绪再挂回路由
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/advisor' },
    { path: '/advisor/:id?', component: AdvisorView, props: true },
  ],
});
