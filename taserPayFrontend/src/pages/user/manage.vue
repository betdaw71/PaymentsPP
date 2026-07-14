<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import ManageMerchants from "@/views/user/headsupport/manage/ManageMerchants.vue"
import ManageSupports from "@/views/user/headsupport/manage/ManageSupports.vue"

const { t } = useI18n()
const authStore = useAuthStore ()
const baseStore = useBaseStore ()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const tabs = ref ([
  {
    icon: 'tabler-coin',
    title: t ('tabs.manage_merchants'),
  },
  {
    icon: 'tabler-lifebuoy',
    title: t ('tabs.manage_supports'),
  },
])

const userTab = ref (null)
</script>

<template>
  <div>
    <VSnackbar
      v-model="snackbar.enabled"
      :color="snackbar.type"
      :timeout="3000"
      top
    >
      {{ snackbar.message }}
    </VSnackbar>
    <VTabs
      v-model="userTab"
      class="v-tabs-pill"
      show-arrows
    >
      <VTab
        v-for="tab in tabs"
        :key="tab.icon"
        class="me-1"
      >
        <VIcon
          :size="18"
          :icon="tab.icon"
          class="me-1"
        />
        <span>{{ tab.title }}</span>
      </VTab>
    </VTabs>

    <VWindow
      v-model="userTab"
      class="mt-6 disable-tab-transition"
      :touch="false"
    >
      <VWindowItem>
        <ManageMerchants />
      </VWindowItem>
      <VWindowItem>
        <ManageSupports />
      </VWindowItem>
    </VWindow>
  </div>
</template>

