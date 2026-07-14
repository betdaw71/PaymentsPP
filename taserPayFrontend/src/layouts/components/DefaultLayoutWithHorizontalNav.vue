<script setup>
import navItems from '@/navigation/horizontal'
import { useThemeConfig } from '@core/composable/useThemeConfig'
import { themeConfig } from '@themeConfig'

// Components
import Footer from '@/layouts/components/Footer.vue'
import NavBarI18n from '@/layouts/components/NavBarI18n.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'
import { HorizontalNavLayout } from '@layouts'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import TraderData from "@/layouts/components/TraderData.vue"
import MerchantData from "@/layouts/components/MerchantData.vue"

const { appRouteTransition } = useThemeConfig()
import { useAuthStore } from "@/stores/useAuthStore"
import { isNavLinkActive } from "@layouts/utils"
import NavBarNotifications from "@/layouts/components/NavBarNotifications.vue"

const authStore = useAuthStore ()

let navItemsFiltered = ref([])
watchEffect(
  () => {
    navItemsFiltered.value = navItems.filter (navItem => (
      !navItem.role ||
      (Number.isInteger(navItem.role) && authStore.userData.role >= navItem.role) ||
      (Array.isArray(navItem.role) && navItem.role.includes(authStore.userData.role))
    ),
    )
  },
)
</script>

<template>
  <HorizontalNavLayout :nav-items="navItemsFiltered">
    <!-- 👉 navbar -->
    <template #navbar>
      <RouterLink
        to="/"
        class="app-logo d-flex align-center gap-x-3"
      >
        <VNodeRenderer :nodes="themeConfig.app.logo" />

        <h1 class="app-title font-weight-bold leading-normal text-xl">
          {{ themeConfig.app.title }}
        </h1>
      </RouterLink>
      <VSpacer />
      <TraderData
        v-if="authStore.is_trader()"
      />
      <MerchantData
        v-if="authStore.is_merchant()"
      />
      <NavBarI18n />
      <template
        v-if="isNavLinkActive({to: 'auth-login'}, $router) || isNavLinkActive({to: 'auth-register'}, $router)"
      />
      <template
        v-else-if="!authStore.userData.role"
      >
        <VBtn
          rounded="lg"
          class="mr-4"
          color="primary"
          :to="{ name: 'auth-login' }"
        >
          Войти
        </VBtn>
      </template>
      <template v-else>
        <NavBarNotifications class="me-2" />
        <UserProfile />
      </template>
    </template>

    <!-- 👉 Pages -->
    <RouterView v-slot="{ Component }">
      <Transition
        :name="appRouteTransition"
        mode="out-in"
      >
        <Component :is="Component" />
      </Transition>
    </RouterView>

    <!-- 👉 Footer -->
    <template #footer>
      <Footer />
    </template>

    <!-- 👉 Customizer -->
  </HorizontalNavLayout>
</template>
