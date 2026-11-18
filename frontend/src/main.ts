import { createApp, h } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory, RouterView } from 'vue-router'
import App from './App.vue'
import './style.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: App },
    { path: '/training', name: 'training', component: App },
    { path: '/report', name: 'report', component: App },
    { path: '/report/evidence/:message', name: 'evidence', component: App },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
createApp({ render: () => h(RouterView) }).use(createPinia()).use(router).mount('#app')
