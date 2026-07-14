/* eslint-disable import/order */
import '@/@iconify/icons-bundle'
import App from '@/App.vue'
import layoutsPlugin from '@/plugins/layouts'
import vuetify from '@/plugins/vuetify'
import { loadFonts } from '@/plugins/webfontloader'
import router from '@/router'
import '@core/scss/template/index.scss'
import '@styles/styles.scss'

import { createPinia } from 'pinia'
import { createApp } from 'vue'
import '@/@fake-db/db'
import { useAuthStore } from '@/stores/useAuthStore'
import setupInterceptors from "@/services/setupInterceptors"
import * as Sentry from "@sentry/vue"
import i18n from "@/plugins/i18n"

loadFonts ()


// Create vue app
const app = createApp (App)

// Use plugins
app.use (vuetify)
app.use (createPinia ())

const authStore = useAuthStore ()

setupInterceptors (authStore)
app.use (router)
app.use (layoutsPlugin)
app.use(i18n)

// Sentry.init({
//   app,
//   dsn: import.meta.env.VITE_SENTRY_API_URL,
//   integrations: [
//     new Sentry.BrowserTracing({
//       routingInstrumentation: Sentry.vueRouterInstrumentation(router),
//     }),
//     new Sentry.Replay(),
//   ],
//
//   // Performance Monitoring
//   tracesSampleRate: 1.0, // Capture 100% of the transactions, reduce in production!
//   // Session Replay
//   replaysSessionSampleRate: 0.1, // This sets the sample rate at 10%. You may want to change it to 100% while in development and then sample at a lower rate in production.
//   replaysOnErrorSampleRate: 1.0, // If you're not already sampling the entire session, change the sample rate to 100% when sampling sessions where errors occur.
// })

// Mount vue app
app.mount ('#app')
