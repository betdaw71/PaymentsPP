<script setup>
import { useBaseStore } from "@/stores/useBaseStore"

const { t } = useI18n()
const baseStore = useBaseStore()

const snackbar = ref({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const empty = () => ({
  cash: '0.00',
  assets: { total: '0.00', psp_total: '0.00', traders_total: '0.00', psp: [], traders: [] },
  liabilities: {
    total: '0.00',
    merchants_total: '0.00',
    agents_total: '0.00',
    teamleads_total: '0.00',
    merchants: [],
    agents: [],
    teamleads: [],
  },
  memo: { rolling_reserve: '0.00', working_deposit: '0.00' },
  pnl: {
    day: { net: '0.00', payin_mdr: '0.00', payin_fx: '0.00', payout_mdr: '0.00', trader_fee: '0.00', agent_fee: '0.00', expenses: '0.00', orders_in: 0, orders_out: 0 },
    month: { net: '0.00', payin_mdr: '0.00', payin_fx: '0.00', payout_mdr: '0.00', trader_fee: '0.00', agent_fee: '0.00', expenses: '0.00', orders_in: 0, orders_out: 0 },
  },
  timezone: 'Europe/Moscow',
})

const data = ref(empty())
const loading = ref(false)

const moneyClass = value => {
  const n = Number(value)
  if (Number.isNaN(n) || n === 0) {
    return ''
  }
  return n > 0 ? 'text-success' : 'text-error'
}

const load = () => {
  loading.value = true
  baseStore.getCashRegister({}).then(response => {
    if (response.error) {
      throw response.error
    }
    data.value = response.data
  }).catch(error => {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: error,
    }
  }).finally(() => {
    loading.value = false
  })
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
      top
    >
      {{ snackbar.message }}
    </VSnackbar>
    <VCard>
      <VCardTitle class="mt-2 ms-2">
        <VAvatar
          size="50"
          variant="text"
          color="primary"
          icon="tabler-report-money"
        />
        {{ t('tabs.cash_register') }}
        <VBtn
          class="float-end"
          icon="tabler-refresh"
          size="small"
          :loading="loading"
          @click="load"
        />
      </VCardTitle>
      <VCardText>
        <div class="text-medium-emphasis mb-4">
          {{ t('cash_register.hint') }} · {{ data.timezone }}
        </div>
        <VRow>
          <VCol
            cols="12"
            md="4"
          >
            <VCard variant="outlined">
              <VCardText>
                <div class="text-caption text-medium-emphasis">
                  {{ t('cash_register.cash') }}
                </div>
                <div
                  class="text-h5 font-weight-medium"
                  :class="moneyClass(data.cash)"
                >
                  {{ data.cash }} USDT
                </div>
                <div class="text-caption mt-1">
                  {{ data.assets.total }} − {{ data.liabilities.total }}
                </div>
              </VCardText>
            </VCard>
          </VCol>
          <VCol
            cols="12"
            md="4"
          >
            <VCard variant="outlined">
              <VCardText>
                <div class="text-caption text-medium-emphasis">
                  {{ t('cash_register.day') }}
                </div>
                <div
                  class="text-h5 font-weight-medium"
                  :class="moneyClass(data.pnl.day.net)"
                >
                  {{ data.pnl.day.net }} USDT
                </div>
                <div class="text-caption mt-1">
                  {{ data.pnl.day.orders_in }} in / {{ data.pnl.day.orders_out }} out
                </div>
              </VCardText>
            </VCard>
          </VCol>
          <VCol
            cols="12"
            md="4"
          >
            <VCard variant="outlined">
              <VCardText>
                <div class="text-caption text-medium-emphasis">
                  {{ t('cash_register.month') }}
                </div>
                <div
                  class="text-h5 font-weight-medium"
                  :class="moneyClass(data.pnl.month.net)"
                >
                  {{ data.pnl.month.net }} USDT
                </div>
                <div class="text-caption mt-1">
                  {{ data.pnl.month.orders_in }} in / {{ data.pnl.month.orders_out }} out
                </div>
              </VCardText>
            </VCard>
          </VCol>
        </VRow>

        <VRow class="mt-2">
          <VCol
            cols="12"
            md="6"
          >
            <div class="text-subtitle-1 font-weight-medium mb-2">
              {{ t('cash_register.assets') }} · {{ data.assets.total }}
            </div>
            <VTable density="compact">
              <thead>
                <tr>
                  <th>{{ t('username') }}</th>
                  <th class="text-end">
                    {{ t('user.balance.available') }}
                  </th>
                  <th class="text-end">
                    {{ t('credit_limit') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in data.assets.psp"
                  :key="`psp-${row.username}`"
                >
                  <td>{{ row.username }}</td>
                  <td
                    class="text-end"
                    :class="moneyClass(row.available)"
                  >
                    {{ row.available }}
                  </td>
                  <td class="text-end">
                    {{ row.credit_limit }}
                  </td>
                </tr>
                <tr
                  v-for="row in data.assets.traders"
                  :key="`tr-${row.username}`"
                >
                  <td>{{ row.username }}</td>
                  <td class="text-end">
                    {{ row.available }}
                  </td>
                  <td class="text-end">
                    —
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCol>
          <VCol
            cols="12"
            md="6"
          >
            <div class="text-subtitle-1 font-weight-medium mb-2">
              {{ t('cash_register.liabilities') }} · {{ data.liabilities.total }}
            </div>
            <VTable density="compact">
              <thead>
                <tr>
                  <th>{{ t('username') }}</th>
                  <th class="text-end">
                    {{ t('user.balance.available') }}
                  </th>
                  <th class="text-end">
                    {{ t('user.balance.frozen') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in data.liabilities.merchants"
                  :key="`m-${row.username}`"
                >
                  <td>{{ row.username }}</td>
                  <td class="text-end">
                    {{ row.available }}
                  </td>
                  <td class="text-end">
                    {{ row.frozen }}
                  </td>
                </tr>
                <tr
                  v-for="row in data.liabilities.agents"
                  :key="`a-${row.username}`"
                >
                  <td>{{ row.username }} ({{ t('roles.agent') }})</td>
                  <td class="text-end">
                    {{ row.available }}
                  </td>
                  <td class="text-end">
                    {{ row.frozen }}
                  </td>
                </tr>
                <tr
                  v-for="row in data.liabilities.teamleads"
                  :key="`t-${row.username}`"
                >
                  <td>{{ row.username }} ({{ t('tabs.team_leads') }})</td>
                  <td class="text-end">
                    {{ row.available }}
                  </td>
                  <td class="text-end">
                    {{ row.frozen }}
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCol>
        </VRow>

        <VRow class="mt-4">
          <VCol cols="12">
            <div class="text-subtitle-1 font-weight-medium mb-2">
              {{ t('cash_register.pnl') }}
            </div>
            <VTable density="compact">
              <thead>
                <tr>
                  <th />
                  <th class="text-end">
                    {{ t('cash_register.day') }}
                  </th>
                  <th class="text-end">
                    {{ t('cash_register.month') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{{ t('cash_register.payin_mdr') }}</td>
                  <td class="text-end">
                    {{ data.pnl.day.payin_mdr }}
                  </td>
                  <td class="text-end">
                    {{ data.pnl.month.payin_mdr }}
                  </td>
                </tr>
                <tr>
                  <td>{{ t('cash_register.payin_fx') }}</td>
                  <td class="text-end">
                    {{ data.pnl.day.payin_fx }}
                  </td>
                  <td class="text-end">
                    {{ data.pnl.month.payin_fx }}
                  </td>
                </tr>
                <tr>
                  <td>{{ t('cash_register.payout_mdr') }}</td>
                  <td class="text-end">
                    {{ data.pnl.day.payout_mdr }}
                  </td>
                  <td class="text-end">
                    {{ data.pnl.month.payout_mdr }}
                  </td>
                </tr>
                <tr>
                  <td>{{ t('cash_register.trader_fee') }}</td>
                  <td class="text-end">
                    {{ data.pnl.day.trader_fee }}
                  </td>
                  <td class="text-end">
                    {{ data.pnl.month.trader_fee }}
                  </td>
                </tr>
                <tr>
                  <td>{{ t('cash_register.agent_fee') }}</td>
                  <td class="text-end">
                    {{ data.pnl.day.agent_fee }}
                  </td>
                  <td class="text-end">
                    {{ data.pnl.month.agent_fee }}
                  </td>
                </tr>
                <tr>
                  <td>{{ t('cash_register.expenses') }}</td>
                  <td class="text-end">
                    {{ data.pnl.day.expenses }}
                  </td>
                  <td class="text-end">
                    {{ data.pnl.month.expenses }}
                  </td>
                </tr>
                <tr>
                  <td class="font-weight-medium">
                    {{ t('cash_register.net') }}
                  </td>
                  <td
                    class="text-end font-weight-medium"
                    :class="moneyClass(data.pnl.day.net)"
                  >
                    {{ data.pnl.day.net }}
                  </td>
                  <td
                    class="text-end font-weight-medium"
                    :class="moneyClass(data.pnl.month.net)"
                  >
                    {{ data.pnl.month.net }}
                  </td>
                </tr>
              </tbody>
            </VTable>
            <div class="text-caption text-medium-emphasis mt-3">
              {{ t('cash_register.memo') }}:
              {{ t('rolling_reserve') }} {{ data.memo.rolling_reserve }},
              {{ t('working_deposit') }} {{ data.memo.working_deposit }}
            </div>
          </VCol>
        </VRow>
      </VCardText>
    </VCard>
  </div>
</template>
