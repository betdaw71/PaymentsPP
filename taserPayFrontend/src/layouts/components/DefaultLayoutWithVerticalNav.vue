<script setup>
import navItems from '@/navigation/vertical'
import { useThemeConfig } from '@core/composable/useThemeConfig'
import Footer from '@/layouts/components/Footer.vue'
import NavBarI18n from '@/layouts/components/NavBarI18n.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'
import ApAppBar from '@/layouts/components/ApAppBar.vue'
import { isNavLinkActive } from '@layouts/utils'
import { useAuthStore } from '@/stores/useAuthStore'
import TraderData from '@/layouts/components/TraderData.vue'
import MerchantData from '@/layouts/components/MerchantData.vue'
import NavBarNotifications from '@/layouts/components/NavBarNotifications.vue'
import { VerticalNavLayout } from '@layouts'

const authStore = useAuthStore ()
const { appRouteTransition, isLessThanOverlayNavBreakpoint, isVerticalNavCollapsed } = useThemeConfig()
const { width: windowWidth } = useWindowSize()

const navItemsFiltered = ref ([])

const handleNavToggle = toggleOverlayFn => {
  if (isLessThanOverlayNavBreakpoint.value(windowWidth.value)) {
    toggleOverlayFn()
  } else {
    isVerticalNavCollapsed.value = !isVerticalNavCollapsed.value
  }
}

watchEffect(
  () => {
    navItemsFiltered.value = navItems.filter (navItem => (
      !navItem.role
        || (Number.isInteger (navItem.role) && authStore.userData.role >= navItem.role)
        || (Array.isArray (navItem.role) && navItem.role.includes (authStore.userData.role))
    ))
  },
)
</script>

<template>
  <VerticalNavLayout :nav-items="navItemsFiltered">
    <template #navbar="{ toggleVerticalOverlayNavActive }">
      <ApAppBar
        show-menu-toggle
        @toggle-nav="handleNavToggle(toggleVerticalOverlayNavActive)"
      >
        <TraderData
          v-if="authStore.is_trader()"
        />
        <MerchantData
          v-if="authStore.is_merchant()"
        />
        <NavBarI18n />
        <template
          v-if="isNavLinkActive({ to: 'auth-login' }, $router) || isNavLinkActive({ to: 'auth-register' }, $router)"
        />
        <template v-else-if="!authStore.userData.role">
          <VBtn
            rounded="lg"
            color="primary"
            :to="{ name: 'auth-login' }"
          >
            Войти
          </VBtn>
        </template>
        <template v-else>
          <NavBarNotifications />
          <UserProfile />
        </template>
      </ApAppBar>
    </template>

    <RouterView v-slot="{ Component }">
      <Transition
        :name="appRouteTransition"
        mode="out-in"
      >
        <Component :is="Component" />
      </Transition>
    </RouterView>

    <template #footer>
      <Footer />
    </template>
  </VerticalNavLayout>
</template>
