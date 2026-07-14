import { setupLayouts } from 'virtual:generated-layouts'
import { createRouter, createWebHistory } from 'vue-router'
import routes from '~pages'
import { themeConfig } from '/themeConfig'
import { useAuthStore } from "@/stores/useAuthStore"
import navigationPermissions from "@/router/navigationPermissions"
import EventBus from "@/services/EventBus"

const router = createRouter ({
  history: createWebHistory (import.meta.env.BASE_URL),
  routes: [
    ...setupLayouts (routes),
  ],
})


router.beforeEach (
  (toRoute, fromRoute, next) => {

    const authStore = useAuthStore ()
    if (!navigationPermissions.paths[toRoute.name]) {
    } else if (navigationPermissions.paths[toRoute.name] === -1 && authStore.userData.role > 0) {
      router.push ({
        name: 'index',
      })
    } else if (Number.isInteger(navigationPermissions.paths[toRoute.name]) && navigationPermissions.paths[toRoute.name] > authStore.userData.role) {
      authStore.authData.nextUrl = toRoute.name
      EventBus.dispatch (authStore.userData.role === 0 ? "register_access" : "subscription_access")
    } else if (Array.isArray(navigationPermissions.paths[toRoute.name]) && !navigationPermissions.paths[toRoute.name].includes(authStore.userData.role)) {
      authStore.authData.nextUrl = toRoute.name
      EventBus.dispatch (authStore.userData.role === 0 ? "register_access" : "subscription_access")
    }

    // window.document.title = toRoute && toRoute.title ? `${toRoute.title} - ${themeConfig.app.title}` : themeConfig.app.title
    next ()
  },
)

export default router
