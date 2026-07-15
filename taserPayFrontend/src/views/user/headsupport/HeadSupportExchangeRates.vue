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
      rates.value = Array.isArray (response.data) ? response.data : []
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
            <VCardText v-if="loading && rates.length === 0">
              {{ $t('data.loading') }}
            </VCardText>
            <VCardText v-else-if="rates.length === 0">
              {{ $t('data.empty') }}
            </VCardText>
            <VTable
              v-else
              class="text-no-wrap"
            >
              <thead>
                <tr>
                  <th scope="col">
                    {{ $t('payment_system') }}
                  </th>
                  <th scope="col">
                    {{ $t('currency') }}
                  </th>
                  <th scope="col">
                    {{ $t('exchange_rate') }}
                  </th>
                  <th scope="col">
                    {{ $t('rate_source') }}
                  </th>
                  <th scope="col">
                    {{ $t('last_update') }}
                  </th>
                  <th scope="col">
                    {{ $t('in_on') }}
                  </th>
                  <th scope="col">
                    {{ $t('out_on') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in rates"
                  :key="item.id"
                >
                  <td>{{ item.name }}</td>
                  <td>{{ item.currency_symbol || '—' }}</td>
                  <td>
                    <span v-if="item.currency_symbol">
                      1 USDT = {{ formatRate(item.usdt_exchange_rate) }} {{ item.currency_symbol }}
                    </span>
                    <span v-else>
                      {{ formatRate(item.usdt_exchange_rate) }}
                    </span>
                  </td>
                  <td>{{ item.rate_source || '—' }}</td>
                  <td>{{ formatLastUpdate(item.last_update) }}</td>
                  <td>
                    <VChip
                      :color="item.in_on ? 'success' : 'error'"
                      size="small"
                      label
                    >
                      {{ item.in_on ? $t('on') : $t('off') }}
                    </VChip>
                  </td>
                  <td>
                    <VChip
                      :color="item.out_on ? 'success' : 'error'"
                      size="small"
                      label
                    >
                      {{ item.out_on ? $t('on') : $t('off') }}
                    </VChip>
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCol>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
