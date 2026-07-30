<script setup>
import { useAuthStore } from '@/stores/useAuthStore'
import { useBaseStore } from '@/stores/useBaseStore'

const authStore = useAuthStore()
const baseStore = useBaseStore()

const scope = computed({
  get: () => baseStore.orders_in_filters.teamleadScope || 'team',
  set: val => {
    baseStore.orders_in_filters.teamleadScope = val
    baseStore.orders_out_filters.teamleadScope = val
  },
})

const show = computed(() =>
  authStore.is_team_lead() && authStore.userData.has_merchant_agent,
)
</script>

<template>
  <VBtnToggle
    v-if="show"
    v-model="scope"
    mandatory
    density="comfortable"
    color="primary"
    class="mb-4"
  >
    <VBtn value="team">
      {{ $t('teamlead_scope_team') }}
    </VBtn>
    <VBtn value="merchant">
      {{ $t('teamlead_scope_merchant') }}
    </VBtn>
  </VBtnToggle>
</template>
