import { createApp } from 'vue'
import { createPinia } from 'pinia'
import i18n from './locales/i18n'
import '@fontsource/outfit/400.css'
import '@fontsource/outfit/500.css'
import '@fontsource/outfit/600.css'
import '@fontsource/outfit/700.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/jetbrains-mono/600.css'
import './style.css'
import './styles/tile.css'   // 统一卡片网格（等宽等高 + 内部滚动）
import App from './App.vue'
import router from './router'
import AppInputNumber from './components/config/AppInputNumber.vue'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
// 全局注册自定义输入框组件
app.component('app-input-number', AppInputNumber)

router.isReady().then(() => {
  app.mount('#app')
})