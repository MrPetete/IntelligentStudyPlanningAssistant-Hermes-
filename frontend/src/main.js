import { createApp } from 'vue'
import App from './App.vue'
import router from './router.js'
import './styles/main.css'

const app = createApp(App)
app.config.errorHandler = (err, instance, info) => {
  console.error('[vue error]', info, err)
}
app.use(router).mount('#app')
