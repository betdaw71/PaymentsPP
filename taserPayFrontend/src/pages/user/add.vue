<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import AddTrader from "@/views/user/headsupport/add/AddTrader.vue"
import AddMerchant from "@/views/user/headsupport/add/AddMerchant.vue"
import AddSupport from "@/views/user/headsupport/add/AddSupport.vue"
import AddTeam from "@/views/user/headsupport/add/AddTeam.vue"

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
    icon: 'tabler-chart-area-line',
    title: t ('tabs.add_trader'),
  },
  {
    icon: 'tabler-coin',
    title: t ('tabs.add_merchant'),
  },
  {
    icon: 'tabler-lifebuoy',
    title: t ('tabs.add_support'),
  },
  {
    icon: 'tabler-users',
    title: t ('tabs.add_team'),
  },
])

const addSettings = ref(
  structuredClone (toRaw (baseStore.add_settings)),
)

watch (
  () => addSettings.value,
  () => {
    baseStore.add_settings = structuredClone (toRaw (addSettings.value))
  },
  { deep: true },
)
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
      v-model="addSettings.tab"
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
      v-model="addSettings.tab"
      class="mt-6 disable-tab-transition"
      :touch="false"
    >
      <VWindowItem>
        <AddTrader />
      </VWindowItem>
      <VWindowItem>
        <AddMerchant />
      </VWindowItem>
      <VWindowItem>
        <AddSupport />
      </VWindowItem>
      <VWindowItem>
        <AddTeam />
      </VWindowItem>
    </VWindow>
  </div>
</template>

