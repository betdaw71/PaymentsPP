<script setup>
import { useTheme } from 'vuetify'
import { useThemeConfig } from '@core/composable/useThemeConfig'
import { hexToRgb } from '@layouts/utils'
import EventBus from "@/services/EventBus"
import { useAuthStore } from "@/stores/useAuthStore"
import navigationPermissions from "@/router/navigationPermissions"

const {
  syncInitialLoaderTheme,
  syncVuetifyThemeWithTheme: syncConfigThemeWithVuetifyTheme,
  isAppRtl,
} = useThemeConfig ()

const userInterval = ref (null)
const { global } = useTheme ()

// ℹ️ Sync current theme with initial loader theme
syncInitialLoaderTheme ()
syncConfigThemeWithVuetifyTheme ()

const router = useRouter ()
const authStore = useAuthStore ()

onMounted (
  () => {
    EventBus.on ("logout", () => {
      authStore.logout ({})
      router.push ({
        name: navigationPermissions.loginPath,
      })
    })
  },
)

onMounted (
  () => {
    EventBus.on ("maintenance_enabled", () => {
      router.push ({
        name: navigationPermissions.maintenancePath,
      })
    })
  },
)
onMounted (
  () => {
    EventBus.on ("maintenance_disabled", () => {
      router.push ({
        name: navigationPermissions.homePath,
      })
    })
  },
)
onBeforeUnmount (
  () => {
    EventBus.remove ("logout")
  },
)

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const loadUser = () => {
  if (authStore.is_authenticated ()) {
    authStore.me ({})
  }
}

onMounted (
  () => {
    loadUser ()
    userInterval.value = setInterval (
      () => {
        loadUser()
      },
      1000 * 30, // 30 seconds
    )
    EventBus.on ("register_access", () => {
      // snackbar.value.enabled = true
      // snackbar.value.type = 'warning'
      // snackbar.value.message = 'Войдите, чтобы получить доступ'
      router.push ({
        name: navigationPermissions.loginPath,
      })
    },
    )
    EventBus.on ("subscription_access", () => {
      // snackbar.value.enabled = true
      // snackbar.value.type = 'success'
      // snackbar.value.message = 'Оформите подписку, чтобы получить доступ'
      router.push ({
        name: 'user',
      })
    },
    )
  },
)
onBeforeUnmount (
  () => {
    EventBus.remove ("register_access")
    EventBus.remove ("subscription_access")
    EventBus.remove ("status_monitor")

    EventBus.remove ("maintenance_enabled")
    EventBus.remove ("maintenance_disabled")
    clearInterval (userInterval.value)
  },
)
</script>

<template>
  <VLocaleProvider :rtl="isAppRtl">
    <!-- ℹ️ This is required to set the background color of active nav link based on currently active global theme's primary -->
    <VApp :style="`--v-global-theme-primary: ${hexToRgb(global.current.value.colors.primary)}`">
      <VSnackbar
        v-model="snackbar.enabled"
        location="bottom end"
        variant="flat"
        transition="scroll-y-reverse-transition"
        :color="snackbar.type"
      >
        {{ snackbar.message }}
      </VSnackbar>
      <RouterView />
    </VApp>
  </VLocaleProvider>
</template>

<style lang="scss">
</style>
