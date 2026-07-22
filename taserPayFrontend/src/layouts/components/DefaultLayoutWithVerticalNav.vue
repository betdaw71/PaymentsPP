<script setup>
import { buildVerticalNavItems } from '@/navigation/vertical/build'
import { useThemeConfig } from '@core/composable/useThemeConfig'

// Components
import Footer from '@/layouts/components/Footer.vue'
import NavBarI18n from '@/layouts/components/NavBarI18n.vue'
import UserProfile from '@/layouts/components/UserProfile.vue'
import { isNavLinkActive } from "@layouts/utils"
import { useAuthStore } from "@/stores/useAuthStore"
import TraderData from "@/layouts/components/TraderData.vue"
import MerchantData from "@/layouts/components/MerchantData.vue"

const authStore = useAuthStore ()

// @layouts plugin
import { VerticalNavLayout } from '@layouts'
import NavBarNotifications from "@/layouts/components/NavBarNotifications.vue"

const { appRouteTransition, isLessThanOverlayNavBreakpoint } = useThemeConfig()
const { width: windowWidth } = useWindowSize()

let navItemsFiltered = ref([])

watchEffect(
  () => {
    navItemsFiltered.value = buildVerticalNavItems(authStore)
  },
)
</script>

<template>
  <VerticalNavLayout :nav-items="navItemsFiltered">
    <!-- 👉 navbar -->
    <template #navbar="{ toggleVerticalOverlayNavActive }">
      <div class="ap-navbar-inner">
        <IconBtn
          v-if="isLessThanOverlayNavBreakpoint(windowWidth)"
          id="vertical-nav-toggle-btn"
          class="ms-n3"
          @click="toggleVerticalOverlayNavActive(true)"
        >
          <VIcon
            size="26"
            icon="lucide:menu"
          />
        </IconBtn>

        <VSpacer />
        <TraderData
          v-if="authStore.is_trader()"
        />
        <MerchantData
          v-if="authStore.is_merchant()"
        />
        <div class="ap-header-tools">
          <NavBarI18n />
          <template
            v-if="isNavLinkActive({to: 'auth-login'}, $router) || isNavLinkActive({to: 'auth-register'}, $router)"
          />
          <template v-else-if="!authStore.userData.role">
            <VBtn
              rounded="lg"
              class="ms-2"
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
        </div>
      </div>
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

  </VerticalNavLayout>
</template>
