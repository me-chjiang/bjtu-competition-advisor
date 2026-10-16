import { createRouter, createWebHashHistory } from 'vue-router';
import AdvisorView from './views/AdvisorView.vue';
import LoginView from './views/LoginView.vue';
import LoginWaitView from './views/LoginWaitView.vue';

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', component: LoginView },
    { path: '/wait', component: LoginWaitView },
    { path: '/advisor/:id?', component: AdvisorView, props: true },
  ],
});
