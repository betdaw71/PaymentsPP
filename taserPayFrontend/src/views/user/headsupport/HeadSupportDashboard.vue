<script setup>
import VueApexCharts from 'vue3-apexcharts'
import { useTheme } from 'vuetify'
import { useBaseStore } from '@/stores/useBaseStore'
import { getAreaChartSplineConfig, getBarChartConfig, getColumnChartConfig } from '@core/libs/apex-chart/apexCharConfig'

const { t } = useI18n ()
const baseStore = useBaseStore ()
const vuetifyTheme = useTheme ()

const loading = ref (false)
const dashboard = ref (null)
const period = ref ('7d')
const paymentSystem = ref (null)
const currency = ref (null)

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: '',
})

const loadMessage = ref ({
  message: t ('data.loading'),
  status: 0,
})

const periodItems = [
  { name: t ('dashboard.period_day'), value: 'day' },
  { name: t ('dashboard.period_7d'), value: '7d' },
  { name: t ('dashboard.period_30d'), value: '30d' },
]

const periodLabel = computed (() => {
  const item = periodItems.find (p => p.value === period.value)

  return item?.name || period.value
})

const paymentSystemItems = computed (() => {
  const all = { name: t ('dashboard.all_payment_systems'), value: null }
  const items = (dashboard.value?.filters?.payment_systems || []).map (
    ps => ({
      name: `${ps.name} (${ps.currency || '?'})`,
      value: ps.id,
    }),
  )

  return [all, ...items]
})

const currencyItems = computed (() => {
  const all = { name: t ('dashboard.all_currencies'), value: null }
  const items = (dashboard.value?.filters?.currencies || []).map (
    c => ({ name: c.symbol, value: c.symbol }),
  )

  return [all, ...items]
})

const fmtUsd = v => {
  if (v === null || v === undefined) {
    return '0.00'
  }

  return Number (v).toLocaleString (undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

const fmtPct = v => `${Number (v || 0).toFixed (1)}%`

const formatLastUpdate = timestamp => {
  if (!timestamp) {
    return t ('rate_not_updated')
  }

  return new Date (timestamp * 1000).toLocaleString ()
}

const kpi = computed (() => dashboard.value?.kpi || {})
const funnelIn = computed (() => dashboard.value?.funnel_in || [])
const funnelOut = computed (() => dashboard.value?.funnel_out || [])
const dailyChart = computed (() => dashboard.value?.daily_chart || [])
const byPaymentSystem = computed (() => dashboard.value?.by_payment_system || [])
const byCurrency = computed (() => dashboard.value?.by_currency || [])
const exchangeRates = computed (() => dashboard.value?.exchange_rates || [])

const queueItems = computed (() => [
  { key: 'manual_check_out', label: 'dashboard.manual_check', color: 'warning' },
  { key: 'arbitrage_in', label: 'dashboard.arbitrage_in', color: 'error' },
  { key: 'arbitrage_out', label: 'dashboard.arbitrage_out', color: 'error' },
  { key: 'cannot_process_in', label: 'dashboard.cannot_process_in', color: 'error' },
  { key: 'cannot_process_out', label: 'dashboard.cannot_process_out', color: 'error' },
])

const turnoverChartSeries = computed (() => [
  { name: t ('dashboard.turnover_in'), data: dailyChart.value.map (d => d.in_usd) },
  { name: t ('dashboard.turnover_out'), data: dailyChart.value.map (d => d.out_usd) },
  { name: t ('dashboard.margin'), data: dailyChart.value.map (d => d.margin) },
])

const turnoverChartOptions = computed (() => {
  const base = getAreaChartSplineConfig (vuetifyTheme.current.value)

  return {
    ...base,
    chart: { ...base.chart, stacked: false },
    xaxis: {
      ...base.xaxis,
      categories: dailyChart.value.map (d => d.date),
    },
    yaxis: {
      labels: {
        formatter: val => `$${Math.round (val)}`,
        style: base.yaxis?.labels?.style,
      },
    },
  }
})

const makeFunnelChart = (title, data) => {
  const base = getBarChartConfig (vuetifyTheme.current.value)

  return {
    series: [{ name: t ('dashboard.orders'), data: data.map (row => row.count) }],
    options: {
      ...base,
      chart: { ...base.chart, type: 'bar' },
      plotOptions: {
        bar: {
          ...base.plotOptions.bar,
          horizontal: true,
        },
      },
      title: { text: title, align: 'left', style: { fontSize: '14px' } },
      xaxis: {
        ...base.xaxis,
        categories: data.map (row => row.status),
      },
    },
  }
}

const funnelInChart = computed (() => makeFunnelChart (t ('dashboard.funnel_in'), funnelIn.value))
const funnelOutChart = computed (() => makeFunnelChart (t ('dashboard.funnel_out'), funnelOut.value))

const psChartSeries = computed (() => [
  { name: t ('dashboard.turnover_in'), data: byPaymentSystem.value.map (r => r.in_completed_usd) },
  { name: t ('dashboard.turnover_out'), data: byPaymentSystem.value.map (r => r.out_completed_usd) },
])

const psChartOptions = computed (() => {
  const base = getColumnChartConfig (vuetifyTheme.current.value)

  return {
    ...base,
    chart: { ...base.chart, stacked: false },
    xaxis: {
      ...base.xaxis,
      categories: byPaymentSystem.value.map (r => `${r.name} (${r.currency || '?'})`),
    },
    yaxis: {
      labels: { formatter: val => `$${Math.round (val)}` },
    },
  }
})

const currencyChartSeries = computed (() => [
  { name: t ('dashboard.turnover_in'), data: byCurrency.value.map (r => r.in_completed_usd) },
  { name: t ('dashboard.turnover_out'), data: byCurrency.value.map (r => r.out_completed_usd) },
])

const currencyChartOptions = computed (() => {
  const base = getColumnChartConfig (vuetifyTheme.current.value)

  return {
    ...base,
    chart: { ...base.chart, stacked: false },
    xaxis: {
      ...base.xaxis,
      categories: byCurrency.value.map (r => r.currency),
    },
    yaxis: {
      labels: { formatter: val => `$${Math.round (val)}` },
    },
  }
})

const fetchDashboard = () => {
  loading.value = true
  loadMessage.value = { message: t ('data.loading'), status: 0 }

  const params = { period: period.value }
  if (paymentSystem.value) {
    params.payment_system = paymentSystem.value
  }
  if (currency.value) {
    params.currency = currency.value
  }

  baseStore.getDashboard (params).then (
    response => {
      if (response.error) {
        throw response.error
      }
      dashboard.value = response.data
      loadMessage.value = { message: '', status: 1 }
    },
  ).catch (
    error => {
      loadMessage.value = { message: t ('data.error'), status: 2 }
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

watch ([period, paymentSystem, currency], fetchDashboard)

onMounted (fetchDashboard)
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
              icon="tabler-chart-dots-3"
            />
            {{ t('tabs.dashboard') }}
          </VCardTitle>

          <VCol cols="12">
            <VCard>
              <!-- Toolbar -->
              <VCardText class="d-flex align-center flex-wrap gap-3">
                <VCardText
                  class="text-h5 mb-0"
                  style="padding: 0.5rem;"
                >
                  {{ t('tabs.dashboard') }}
                  <VTooltip location="right">
                    <template #activator="{ props }">
                      <VChip
                        v-bind="props"
                        class="ms-1 p-1 font-weight-bold"
                        color="success"
                        text-color="white"
                        small
                      >
                        $ {{ fmtUsd(kpi.in_turnover_usd + kpi.out_turnover_usd) }}
                      </VChip>
                    </template>
                    <span>{{ t('dashboard.turnover_total') }}</span>
                  </VTooltip>
                  <VTooltip location="right">
                    <template #activator="{ props }">
                      <VChip
                        v-bind="props"
                        class="ms-1 p-1 font-weight-bold"
                        color="primary"
                        text-color="white"
                        small
                      >
                        $ {{ fmtUsd(kpi.margin_usd) }}
                      </VChip>
                    </template>
                    <span>{{ t('dashboard.margin') }}</span>
                  </VTooltip>
                  <VTooltip location="right">
                    <template #activator="{ props }">
                      <VChip
                        v-bind="props"
                        class="ms-1 p-1 font-weight-bold"
                        color="warning"
                        text-color="white"
                        small
                      >
                        {{ kpi.pending_withdrawals || 0 }}
                      </VChip>
                    </template>
                    <span>{{ t('dashboard.pending_withdrawals') }}</span>
                  </VTooltip>
                </VCardText>

                <VSpacer />

                <VBtn
                  icon="tabler-refresh"
                  size="small"
                  :loading="loading"
                  @click="fetchDashboard"
                />
              </VCardText>

              <!-- Filters -->
              <VCardText>
                <VRow>
                  <VCol
                    cols="12"
                    sm="4"
                    md="3"
                  >
                    <AppSelect
                      v-model="period"
                      :label="t('dashboard.period')"
                      :items="periodItems"
                      item-title="name"
                      item-value="value"
                    />
                  </VCol>
                  <VCol
                    cols="12"
                    sm="4"
                    md="4"
                  >
                    <AppSelect
                      v-model="paymentSystem"
                      :label="t('payment_system')"
                      :items="paymentSystemItems"
                      item-title="name"
                      item-value="value"
                      clearable
                      clear-icon="tabler-x"
                    />
                  </VCol>
                  <VCol
                    cols="12"
                    sm="4"
                    md="3"
                  >
                    <AppSelect
                      v-model="currency"
                      :label="t('currency')"
                      :items="currencyItems"
                      item-title="name"
                      item-value="value"
                      clearable
                      clear-icon="tabler-x"
                    />
                  </VCol>
                  <VCol
                    cols="12"
                    sm="4"
                    md="2"
                    class="d-flex align-center"
                  >
                    <VBtn
                      color="primary"
                      prepend-icon="tabler-search"
                      block
                      @click="fetchDashboard"
                    >
                      {{ t('search') }}
                    </VBtn>
                  </VCol>
                </VRow>
              </VCardText>

              <VDivider />

              <template v-if="loading && !dashboard">
                <VCardItem>
                  <div class="text-center text-body-1 justify-center align-center">
                    {{ loadMessage.message }}
                    <VProgressCircular
                      :width="3"
                      color="primary"
                      indeterminate
                    />
                  </div>
                </VCardItem>
              </template>

              <template v-else-if="dashboard">
                <!-- KPI row -->
                <VCardText>
                  <VRow>
                    <VCol
                      cols="12"
                      sm="6"
                      md="3"
                    >
                      <div class="text-caption text-medium-emphasis">
                        {{ t('dashboard.turnover_in') }}
                      </div>
                      <div class="text-h6">
                        $ {{ fmtUsd(kpi.in_turnover_usd) }}
                      </div>
                      <div class="text-caption">
                        {{ kpi.in_completed }} / {{ kpi.in_created }} · {{ fmtPct(kpi.in_conversion) }}
                      </div>
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                      md="3"
                    >
                      <div class="text-caption text-medium-emphasis">
                        {{ t('dashboard.turnover_out') }}
                      </div>
                      <div class="text-h6">
                        $ {{ fmtUsd(kpi.out_turnover_usd) }}
                      </div>
                      <div class="text-caption">
                        {{ kpi.out_completed }} / {{ kpi.out_created }} · {{ fmtPct(kpi.out_conversion) }}
                      </div>
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                      md="3"
                    >
                      <div class="text-caption text-medium-emphasis">
                        {{ t('tabs.traders_balance') }}
                      </div>
                      <div class="text-body-1">
                        <VChip
                          class="me-1"
                          color="success"
                          size="small"
                          label
                        >
                          $ {{ fmtUsd(kpi.traders_available) }}
                        </VChip>
                        <VChip
                          color="info"
                          size="small"
                          label
                          append-icon="tabler-snowflake"
                        >
                          $ {{ fmtUsd(kpi.traders_frozen) }}
                        </VChip>
                      </div>
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                      md="3"
                    >
                      <div class="text-caption text-medium-emphasis">
                        {{ t('tabs.merchants_balance') }}
                      </div>
                      <div class="text-body-1">
                        <VChip
                          class="me-1"
                          color="success"
                          size="small"
                          label
                        >
                          $ {{ fmtUsd(kpi.merchants_available) }}
                        </VChip>
                        <VChip
                          color="info"
                          size="small"
                          label
                          append-icon="tabler-snowflake"
                        >
                          $ {{ fmtUsd(kpi.merchants_frozen) }}
                        </VChip>
                      </div>
                    </VCol>
                  </VRow>
                </VCardText>

                <VDivider />

                <!-- Queues -->
                <VCardText class="d-flex flex-wrap gap-2">
                  <VChip
                    v-for="item in queueItems"
                    :key="item.key"
                    :color="kpi[item.key] > 0 ? item.color : 'default'"
                    variant="tonal"
                    label
                  >
                    {{ t(item.label) }}: {{ kpi[item.key] || 0 }}
                  </VChip>
                  <VChip
                    color="secondary"
                    variant="tonal"
                    label
                  >
                    {{ t('dashboard.period') }}: {{ periodLabel }}
                  </VChip>
                </VCardText>

                <VDivider />

                <!-- Daily chart -->
                <VCardText>
                  <div class="text-h6 mb-3">
                    {{ t('dashboard.daily_turnover') }}
                  </div>
                  <VueApexCharts
                    v-if="dailyChart.length"
                    type="area"
                    height="320"
                    :series="turnoverChartSeries"
                    :options="turnoverChartOptions"
                  />
                  <div
                    v-else
                    class="text-center text-medium-emphasis pa-8"
                  >
                    {{ t('data.empty') }}
                  </div>
                </VCardText>

                <VDivider />

                <!-- Funnels -->
                <VCardText>
                  <VRow>
                    <VCol
                      cols="12"
                      md="6"
                    >
                      <VueApexCharts
                        v-if="funnelIn.length"
                        type="bar"
                        height="280"
                        :series="funnelInChart.series"
                        :options="funnelInChart.options"
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      md="6"
                    >
                      <VueApexCharts
                        v-if="funnelOut.length"
                        type="bar"
                        height="280"
                        :series="funnelOutChart.series"
                        :options="funnelOutChart.options"
                      />
                    </VCol>
                  </VRow>
                </VCardText>

                <VDivider />

                <!-- By payment system -->
                <VCardText>
                  <div class="text-h6 mb-3">
                    {{ t('dashboard.by_payment_system') }}
                  </div>
                  <VueApexCharts
                    v-if="byPaymentSystem.length"
                    type="bar"
                    height="280"
                    :series="psChartSeries"
                    :options="psChartOptions"
                    class="mb-4"
                  />
                  <VTable class="text-no-wrap invoice-list-table">
                    <thead>
                      <tr>
                        <th scope="col">{{ t('payment_system').toUpperCase() }}</th>
                        <th scope="col">{{ t('currency').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.in_orders').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.in_completed').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.in_usd').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.out_orders').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.out_completed').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.out_usd').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.margin').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.conversion').toUpperCase() }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="row in byPaymentSystem"
                        :key="row.id"
                      >
                        <td>{{ row.name }}</td>
                        <td>{{ row.currency || '—' }}</td>
                        <td>{{ row.in_count }}</td>
                        <td>{{ row.in_completed }}</td>
                        <td>$ {{ fmtUsd(row.in_completed_usd) }}</td>
                        <td>{{ row.out_count }}</td>
                        <td>{{ row.out_completed }}</td>
                        <td>$ {{ fmtUsd(row.out_completed_usd) }}</td>
                        <td>$ {{ fmtUsd(row.margin) }}</td>
                        <td>In {{ fmtPct(row.in_conversion) }} / Out {{ fmtPct(row.out_conversion) }}</td>
                      </tr>
                      <tr v-if="!byPaymentSystem.length">
                        <td
                          colspan="10"
                          class="text-center text-medium-emphasis"
                        >
                          {{ t('data.empty') }}
                        </td>
                      </tr>
                    </tbody>
                  </VTable>
                </VCardText>

                <VDivider />

                <!-- By currency -->
                <VCardText>
                  <div class="text-h6 mb-3">
                    {{ t('dashboard.by_currency') }}
                  </div>
                  <VueApexCharts
                    v-if="byCurrency.length"
                    type="bar"
                    height="260"
                    :series="currencyChartSeries"
                    :options="currencyChartOptions"
                    class="mb-4"
                  />
                  <VTable class="text-no-wrap invoice-list-table">
                    <thead>
                      <tr>
                        <th scope="col">{{ t('currency').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.in_orders').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.in_completed').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.in_usd').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.out_orders').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.out_completed').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.out_usd').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.margin').toUpperCase() }}</th>
                        <th scope="col">{{ t('dashboard.conversion').toUpperCase() }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="row in byCurrency"
                        :key="row.currency"
                      >
                        <td>{{ row.currency }}</td>
                        <td>{{ row.in_count }}</td>
                        <td>{{ row.in_completed }}</td>
                        <td>$ {{ fmtUsd(row.in_completed_usd) }}</td>
                        <td>{{ row.out_count }}</td>
                        <td>{{ row.out_completed }}</td>
                        <td>$ {{ fmtUsd(row.out_completed_usd) }}</td>
                        <td>$ {{ fmtUsd(row.margin) }}</td>
                        <td>In {{ fmtPct(row.in_conversion) }} / Out {{ fmtPct(row.out_conversion) }}</td>
                      </tr>
                      <tr v-if="!byCurrency.length">
                        <td
                          colspan="9"
                          class="text-center text-medium-emphasis"
                        >
                          {{ t('data.empty') }}
                        </td>
                      </tr>
                    </tbody>
                  </VTable>
                </VCardText>

                <VDivider />

                <!-- Exchange rates -->
                <VCardText>
                  <div class="text-h6 mb-3">
                    {{ t('tabs.exchange_rates') }}
                  </div>
                  <VTable class="text-no-wrap invoice-list-table">
                    <thead>
                      <tr>
                        <th scope="col">{{ t('payment_system').toUpperCase() }}</th>
                        <th scope="col">{{ t('currency').toUpperCase() }}</th>
                        <th scope="col">{{ t('exchange_rate').toUpperCase() }}</th>
                        <th scope="col">{{ t('rate_source').toUpperCase() }}</th>
                        <th scope="col">{{ t('last_update').toUpperCase() }}</th>
                        <th scope="col">{{ t('in_on').toUpperCase() }}</th>
                        <th scope="col">{{ t('out_on').toUpperCase() }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="rate in exchangeRates"
                        :key="rate.id"
                      >
                        <td>{{ rate.name }}</td>
                        <td>{{ rate.currency_symbol || '—' }}</td>
                        <td>
                          <span v-if="rate.currency_symbol">
                            1 USDT = {{ fmtUsd(rate.usdt_exchange_rate) }} {{ rate.currency_symbol }}
                          </span>
                          <span v-else>{{ fmtUsd(rate.usdt_exchange_rate) }}</span>
                        </td>
                        <td>{{ rate.rate_source || '—' }}</td>
                        <td>{{ formatLastUpdate(rate.last_update) }}</td>
                        <td>
                          <VChip
                            :color="rate.in_on ? 'success' : 'error'"
                            size="small"
                            label
                          >
                            {{ rate.in_on ? t('on') : t('off') }}
                          </VChip>
                        </td>
                        <td>
                          <VChip
                            :color="rate.out_on ? 'success' : 'error'"
                            size="small"
                            label
                          >
                            {{ rate.out_on ? t('on') : t('off') }}
                          </VChip>
                        </td>
                      </tr>
                      <tr v-if="!exchangeRates.length">
                        <td
                          colspan="7"
                          class="text-center text-medium-emphasis"
                        >
                          {{ t('data.empty') }}
                        </td>
                      </tr>
                    </tbody>
                  </VTable>
                </VCardText>
              </template>
            </VCard>
          </VCol>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
