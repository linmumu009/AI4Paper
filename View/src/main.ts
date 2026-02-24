import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { initTheme } from './stores/theme'
import './style.css'

// 在 Vue mount 前初始化主题，避免闪白/闪黑
initTheme()

const app = createApp(App)
app.use(router)
app.mount('#app')
