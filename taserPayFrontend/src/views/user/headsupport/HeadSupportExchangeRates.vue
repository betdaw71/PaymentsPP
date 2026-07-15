<script setup>
import { useBaseStore } from '@/stores/useBaseStore'

const { t } = useI18n ()
const baseStore = useBaseStore ()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: '',
})

const rates = ref ([])
const loading = ref (false)
let pollingTimer = null

const headers = computed (() => [
  { title: t ('payment_system'), key: 'name' },
  { title: t ('currency'), key: 'currency_symbol' },
  { title: t ('exchange_rate'), key: 'usdt_exchange_rate' },
  { title: t ('rate_source'), key: 'rate_source' },
  { title: t ('last_update'), key: 'last_update' },
  { title: t ('in_on'), key: 'in_on' },
  { title: t ('out_on'), key: 'out_on' },
])

const formatRate = rate => {
  if (rate === null || rate === undefined) {
    return '—'
  }

  return Number (rate).toLocaleString (undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

const formatLastUpdate = timestamp => {
  if (!timestamp) {
    return t ('rate_not_updated')
  }

  return new Date (timestamp * 1000).toLocaleString ()
}

const fetchRates = () => {
  loading.value = true
  baseStore.getExchangeRates ({}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      rates.value = response.data
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: typeof error === 'string' ? error : t ('data.error'),
      }
    },
  ).finally (
    () => {
      loading.value = false
    },
  )
}

onMounted (
  () => {
    fetchRates ()
    pollingTimer = setInterval (fetchRates, 60000)
  },
)

onBeforeUnmount (
  () => {
    if (pollingTimer) {
      clearInterval (pollingTimer)
    }
  },
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
    <VRow>
      <VCol cols="12">
        <VCard>
          <VCardTitle class="mt-2 ms-2">
            <VAvatar
              size="50"
              variant="text"
              color="primary"
              icon="tabler-currency-dollar"
            />
            {{ $t('tabs.exchange_rates') }}
            <VBtn
              class="float-end"
              icon="tabler-refresh"
              size="small"
              :loading="loading"
              @click="fetchRates"
            />
          </VCardTitle>
          <VCol cols="12">
            <VDataTable
              :headers="headers"
              :items="rates"
              :loading="loading"
              item-value="id"
              class="text-no-wrap"
            >
              <template #item.usdt_exchange_rate="{ item }">
                <span v-if="item.currency_symbol">
                  1 USDT = {{ formatRate(item.usdt_exchange_rate) }} {{ item.currency_symbol }}
                </span>
                <span v-else>
                  {{ formatRate(item.usdt_exchange_rate) }}
                </span>
              </template>
              <template #item.rate_source="{ item }">
                {{ item.rate_source || '—' }}
              </template>
              <template #item.last_update="{ item }">
                {{ formatLastUpdate(item.last_update) }}
              </template>
              <template #item.in_on="{ item }">
                <VChip
                  :color="item.in_on ? 'success' : 'error'"
                  size="small"
                  label
                >
                  {{ item.in_on ? $t('on') : $t('off') }}
                </VChip>
              </template>
              <template #item.out_on="{ item }">
                <VChip
                  :color="item.out_on ? 'success' : 'error'"
                  size="small"
                  label
                >
                  {{ item.out_on ? $t('on') : $t('off') }}
                </VChip>
              </template>
            </VDataTable>
          </VCol>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
