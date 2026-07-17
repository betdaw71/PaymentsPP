<script setup>
import VueApexCharts from 'vue3-apexcharts'
import { useTheme } from 'vuetify'
import { hexToRgb } from '@layouts/utils'
import { useBaseStore } from '@/stores/useBaseStore'

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

const truthMetrics = computed (() => [
  {
    label: t ('dashboard.turnover_in'),
    value: `$ ${fmtUsd (kpi.value.in_turnover_usd)}`,
    hint: `${fmtPct (kpi.value.in_conversion)} conv`,
    tone: 'primary',
  },
  {
    label: t ('dashboard.turnover_out'),
    value: `$ ${fmtUsd (kpi.value.out_turnover_usd)}`,
    hint: `${fmtPct (kpi.value.out_conversion)} conv`,
    tone: 'primary',
  },
  {
    label: t ('dashboard.margin'),
    value: `$ ${fmtUsd (kpi.value.margin_usd)}`,
    tone: 'success',
  },
  {
    label: t ('dashboard.pending_withdrawals'),
    value: String (kpi.value.pending_withdrawals || 0),
    hint: `$ ${fmtUsd (kpi.value.pending_withdrawals_usd)}`,
    tone: kpi.value.pending_withdrawals > 0 ? 'warning' : 'secondary',
    icon: 'tabler-cash-banknote',
    alert: kpi.value.pending_withdrawals > 0,
  },
])

const queueAlerts = computed (() => queueItems.value.map (item => ({
  label: t (item.label),
  count: kpi.value[item.key] || 0,
  tone: item.color,
})))

const themeColors = computed (() => vuetifyTheme.current.value.colors)

const chartPalette = computed (() => [
  themeColors.value.primary,
  themeColors.value.info,
  themeColors.value.success,
])

const chartUi = computed (() => {
  const theme = vuetifyTheme.current.value
  const labelColor = `rgba(${hexToRgb(theme.colors['on-surface'])},${theme.variables['medium-emphasis-opacity']})`
  const borderColor = `rgba(${hexToRgb(String(theme.variables['border-color']))},${theme.variables['border-opacity']})`

  return { labelColor, borderColor }
})

const buildChartOptions = (categories = [], horizontal = false) => ({
  chart: {
    parentHeightOffset: 0,
    toolbar: { show: false },
    fontFamily: 'inherit',
  },
  colors: chartPalette.value,
  dataLabels: { enabled: false },
  stroke: {
    curve: 'smooth',
    width: horizontal ? 0 : 2,
  },
  grid: {
    borderColor: chartUi.value.borderColor,
    strokeDashArray: 4,
    xaxis: { lines: { show: !horizontal } },
    yaxis: { lines: { show: horizontal } },
  },
  legend: {
    position: 'top',
    horizontalAlign: 'left',
    fontSize: '13px',
    fontWeight: 500,
    labels: { colors: chartUi.value.labelColor },
    markers: { offsetX: -3, radius: 12 },
  },
  plotOptions: {
    bar: {
      horizontal,
      borderRadius: 8,
      borderRadiusApplication: 'end',
      columnWidth: horizontal ? '30%' : '45%',
      barHeight: horizontal ? '30%' : undefined,
    },
  },
  xaxis: {
    categories,
    axisBorder: { show: false },
    axisTicks: { color: chartUi.value.borderColor },
    labels: {
      style: { colors: chartUi.value.labelColor, fontSize: '0.8125rem' },
      rotate: horizontal ? 0 : -35,
    },
  },
  yaxis: {
    labels: {
      style: { colors: chartUi.value.labelColor, fontSize: '0.8125rem' },
      formatter: val => `$${Math.round (val)}`,
    },
  },
  fill: {
    type: horizontal ? 'solid' : 'gradient',
    opacity: horizontal ? 1 : 0.85,
    gradient: {
      shadeIntensity: 0.35,
      opacityFrom: 0.45,
      opacityTo: 0.05,
      stops: [0, 90, 100],
    },
  },
  tooltip: {
    theme: vuetifyTheme.current.value.dark ? 'dark' : 'light',
  },
})

const turnoverChartSeries = computed (() => [
  { name: t ('dashboard.turnover_in'), data: dailyChart.value.map (d => d.in_usd) },
  { name: t ('dashboard.turnover_out'), data: dailyChart.value.map (d => d.out_usd) },
  { name: t ('dashboard.margin'), data: dailyChart.value.map (d => d.margin) },
])

const turnoverChartOptions = computed (() =>
  buildChartOptions (dailyChart.value.map (d => d.date), false),
)

const funnelInChart = computed (() => ({
  series: [{ name: t ('dashboard.orders'), data: funnelIn.value.map (r => r.count) }],
  options: {
    ...buildChartOptions (funnelIn.value.map (r => r.status), true),
    colors: [themeColors.value.primary],
    title: {
      text: t ('dashboard.funnel_in'),
      align: 'left',
      style: { fontSize: '15px', fontWeight: 600, color: chartUi.value.labelColor },
    },
  },
}))

const funnelOutChart = computed (() => ({
  series: [{ name: t ('dashboard.orders'), data: funnelOut.value.map (r => r.count) }],
  options: {
    ...buildChartOptions (funnelOut.value.map (r => r.status), true),
    colors: [themeColors.value.primary],
    title: {
      text: t ('dashboard.funnel_out'),
      align: 'left',
      style: { fontSize: '15px', fontWeight: 600, color: chartUi.value.labelColor },
    },
  },
}))

const psChartSeries = computed (() => [
  { name: t ('dashboard.turnover_in'), data: byPaymentSystem.value.map (r => r.in_completed_usd) },
  { name: t ('dashboard.turnover_out'), data: byPaymentSystem.value.map (r => r.out_completed_usd) },
])

const psChartOptions = computed (() =>
  buildChartOptions (
    byPaymentSystem.value.map (r => `${r.name} (${r.currency || '?'})`),
    false,
  ),
)

const currencyChartSeries = computed (() => [
  { name: t ('dashboard.turnover_in'), data: byCurrency.value.map (r => r.in_completed_usd) },
  { name: t ('dashboard.turnover_out'), data: byCurrency.value.map (r => r.out_completed_usd) },
])

const currencyChartOptions = computed (() =>
  buildChartOptions (byCurrency.value.map (r => r.currency), false),
)

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

    <ApWorkspace embedded>
      <div class="ap-filter-toolbar mb-3">
        <VSpacer />
        <VBtn
          icon="tabler-refresh"
          size="small"
          variant="tonal"
          :loading="loading"
          @click="fetchDashboard"
        />
      </div>

      <ApFilterPanel class="mb-3">
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
      </ApFilterPanel>

      <template v-if="loading && !dashboard">
        <div class="ap-micro-loading pa-6 justify-center">
          {{ loadMessage.message }}
          <VProgressCircular
            :width="3"
            color="primary"
            indeterminate
            size="20"
          />
        </div>
      </template>

      <template v-else-if="dashboard">
        <ApTruthStrip :items="truthMetrics" />
        <ApQueueStrip
          class="mt-3 mb-2"
          :items="queueAlerts"
        />

        <ApBlock :title="t('dashboard.daily_turnover')">
          <VueApexCharts
            v-if="dailyChart.length"
            type="area"
            height="320"
            :series="turnoverChartSeries"
            :options="turnoverChartOptions"
          />
          <div
            v-else
            class="text-center text-body-1 text-medium-emphasis pa-8"
          >
            {{ t('data.empty') }}
          </div>
        </ApBlock>

        <ApBlock :title="`${t('dashboard.funnel_in')} / ${t('dashboard.funnel_out')}`">
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
        </ApBlock>

        <ApBlock :title="t('dashboard.by_payment_system')">
          <VueApexCharts
            v-if="byPaymentSystem.length"
            type="bar"
            height="280"
            :series="psChartSeries"
            :options="psChartOptions"
            class="mb-4"
          />
          <ApDataGrid>
            <thead>
              <tr>
                <th scope="col">{{ t('payment_system') }}</th>
                <th scope="col">{{ t('currency') }}</th>
                <th scope="col">{{ t('dashboard.in_orders') }}</th>
                <th scope="col">{{ t('dashboard.in_completed') }}</th>
                <th scope="col">{{ t('dashboard.in_usd') }}</th>
                <th scope="col">{{ t('dashboard.out_orders') }}</th>
                <th scope="col">{{ t('dashboard.out_completed') }}</th>
                <th scope="col">{{ t('dashboard.out_usd') }}</th>
                <th scope="col">{{ t('dashboard.margin') }}</th>
                <th scope="col">{{ t('dashboard.conversion') }}</th>
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
          </ApDataGrid>
        </ApBlock>

        <ApBlock :title="t('dashboard.by_currency')">
          <VueApexCharts
            v-if="byCurrency.length"
            type="bar"
            height="260"
            :series="currencyChartSeries"
            :options="currencyChartOptions"
            class="mb-4"
          />
          <ApDataGrid>
            <thead>
              <tr>
                <th scope="col">{{ t('currency') }}</th>
                <th scope="col">{{ t('dashboard.in_orders') }}</th>
                <th scope="col">{{ t('dashboard.in_completed') }}</th>
                <th scope="col">{{ t('dashboard.in_usd') }}</th>
                <th scope="col">{{ t('dashboard.out_orders') }}</th>
                <th scope="col">{{ t('dashboard.out_completed') }}</th>
                <th scope="col">{{ t('dashboard.out_usd') }}</th>
                <th scope="col">{{ t('dashboard.margin') }}</th>
                <th scope="col">{{ t('dashboard.conversion') }}</th>
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
          </ApDataGrid>
        </ApBlock>

        <ApBlock :title="t('tabs.exchange_rates')">
          <ApDataGrid>
            <thead>
              <tr>
                <th scope="col">{{ t('payment_system') }}</th>
                <th scope="col">{{ t('currency') }}</th>
                <th scope="col">{{ t('exchange_rate') }}</th>
                <th scope="col">{{ t('rate_source') }}</th>
                <th scope="col">{{ t('last_update') }}</th>
                <th scope="col">{{ t('in_on') }}</th>
                <th scope="col">{{ t('out_on') }}</th>
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
                  <ApStatusBadge
                    :label="rate.in_on ? t('on') : t('off')"
                    :color="rate.in_on ? 'success' : 'error'"
                    variant="tonal"
                  />
                </td>
                <td>
                  <ApStatusBadge
                    :label="rate.out_on ? t('on') : t('off')"
                    :color="rate.out_on ? 'success' : 'error'"
                    variant="tonal"
                  />
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
          </ApDataGrid>
        </ApBlock>
      </template>
    </ApWorkspace>
  </div>
</template>
