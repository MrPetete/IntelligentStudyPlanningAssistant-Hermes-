import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import i18n from './i18n.js'
import './styles/main.css'

const app = createApp(App)
app.config.errorHandler = (err, instance, info) => {
  console.error('[vue error]', info, err)
}
app.use(router).use(i18n).mount('#app')
