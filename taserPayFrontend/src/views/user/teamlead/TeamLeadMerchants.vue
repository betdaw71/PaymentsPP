<script setup>
import { useMerchantStore } from '@/stores/useMerchantStore'
import { useRouter } from 'vue-router'

const merchantStore = useMerchantStore()
const router = useRouter()

const snackbar = ref({
  enabled: false,
  type: 'error',
  message: '',
})

const items = ref([])

const normalizeList = data => {
  if (data?.results)
    return data.results
  return Array.isArray(data) ? data : []
}

const load = () => {
  merchantStore.getMerchantAgentAssignments({ per_page: 100 }).then(response => {
    if (response.error) {
      snackbar.value = { enabled: true, type: 'error', message: String(response.error) }
      return
    }
    items.value = normalizeList(response.data)
  })
}

const openOrdersIn = () => {
  router.push({ name: 'orders-in-type', params: { type: 'all' }, query: { teamlead_scope: 'merchant' } })
}

const openOrdersOut = () => {
  router.push({ name: 'orders-out-type', params: { type: 'all' }, query: { teamlead_scope: 'merchant' } })
}

onMounted(() => {
  load()
})
</script>

<template>
  <div>
    <VSnackbar
      v-model="snackbar.enabled"
      :color="snackbar.type"
      :timeout="3000"
      location="top"
    >
      {{ snackbar.message }}
    </VSnackbar>

    <VCard>
      <VCardTitle class="mt-2 ms-2 d-flex align-center flex-wrap gap-2">
        <VAvatar
          size="50"
          variant="text"
          color="primary"
          icon="tabler-building-store"
        />
        {{ $t('tabs.agent_merchants') }}
        <VSpacer />
        <VBtn
          size="small"
          variant="tonal"
          @click="openOrdersIn"
        >
          {{ $t('tabs.orders_in') }}
        </VBtn>
        <VBtn
          size="small"
          variant="tonal"
          @click="openOrdersOut"
        >
          {{ $t('tabs.orders_out') }}
        </VBtn>
        <VBtn
          icon="tabler-refresh"
          size="small"
          variant="text"
          @click="load"
        />
      </VCardTitle>

      <VCardText>
        <p class="text-body-2 text-medium-emphasis mb-4">
          {{ $t('merchant_agent.cabinet_hint') }}
        </p>
        <VTable>
          <thead>
            <tr>
              <th>{{ $t('merchant') }}</th>
              <th>{{ $t('merchant_agent.turnover_in') }}</th>
              <th>{{ $t('merchant_agent.turnover_out') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in items"
              :key="row.id"
            >
              <td>{{ row.merchant_username }}</td>
              <td>{{ row.turnover_percent_in }}%</td>
              <td>{{ row.turnover_percent_out }}%</td>
            </tr>
            <tr v-if="items.length === 0">
              <td
                colspan="3"
                class="text-center text-medium-emphasis py-6"
              >
                {{ $t('merchant_agent.no_assignments') }}
              </td>
            </tr>
          </tbody>
        </VTable>
      </VCardText>
    </VCard>
  </div>
</template>
