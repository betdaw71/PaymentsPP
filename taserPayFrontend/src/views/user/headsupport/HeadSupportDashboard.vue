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

    <UiWorkspace>
      <template #header>
        <div class="ui-workspace__title-row">
          <VAvatar
            size="40"
            variant="text"
            color="primary"
            icon="lucide:layout-dashboard"
          />
          <h1 class="ui-workspace__title">
            {{ t('tabs.dashboard') }}
          </h1>
        </div>
      </template>

      <template #actions>
        <UiButton
          variant="ghost"
          size="small"
          icon
          :loading="loading"
          @click="fetchDashboard"
        >
          <VIcon
            icon="lucide:refresh-cw"
            size="16"
          />
        </UiButton>
      </template>

      <div class="ui-orders-filter-zone">
        <div class="ui-orders-search">
          <div class="ui-orders-search__field">
            <AppSelect
              v-model="period"
              :label="t('dashboard.period')"
              :items="periodItems"
              item-title="name"
              item-value="value"
              density="compact"
            />
          </div>
          <div class="ui-orders-search__field">
            <AppSelect
              v-model="paymentSystem"
              :label="t('payment_system')"
              :items="paymentSystemItems"
              item-title="name"
              item-value="value"
              clearable
              clear-icon="lucide:x"
              density="compact"
            />
          </div>
          <div class="ui-orders-search__field">
            <AppSelect
              v-model="currency"
              :label="t('currency')"
              :items="currencyItems"
              item-title="name"
              item-value="value"
              clearable
              clear-icon="lucide:x"
              density="compact"
            />
          </div>
          <UiButton
            variant="primary"
            size="small"
            :loading="loading"
            @click="fetchDashboard"
          >
            <VIcon
              icon="lucide:search"
              size="16"
              start
            />
            {{ t('search') }}
          </UiButton>
        </div>
      </div>

      <div
        v-if="loading && !dashboard"
        class="ui-dashboard__loading"
      >
        <span>{{ loadMessage.message }}</span>
        <VProgressCircular
          :width="3"
          size="24"
          color="primary"
          indeterminate
        />
      </div>

      <template v-else-if="dashboard">
        <div class="ui-orders-metrics ui-orders-metrics--above-table">
          <VTooltip location="bottom">
            <template #activator="{ props }">
              <VChip
                v-bind="props"
                class="px-3 font-weight-bold"
                color="primary"
                text-color="white"
                size="default"
              >
                $ {{ fmtUsd(kpi.in_turnover_usd) }}
              </VChip>
            </template>
            <span>{{ t('dashboard.turnover_in') }} · {{ fmtPct(kpi.in_conversion) }}</span>
          </VTooltip>

          <VTooltip location="bottom">
            <template #activator="{ props }">
              <VChip
                v-bind="props"
                class="px-3 font-weight-bold"
                color="primary"
                text-color="white"
                size="default"
              >
                $ {{ fmtUsd(kpi.out_turnover_usd) }}
              </VChip>
            </template>
            <span>{{ t('dashboard.turnover_out') }} · {{ fmtPct(kpi.out_conversion) }}</span>
          </VTooltip>

          <VTooltip location="bottom">
            <template #activator="{ props }">
              <VChip
                v-bind="props"
                class="px-3 font-weight-bold"
                color="primary"
                text-color="white"
                size="default"
              >
                $ {{ fmtUsd(kpi.margin_usd) }}
              </VChip>
            </template>
            <span>{{ t('dashboard.margin') }}</span>
          </VTooltip>

          <VTooltip location="bottom">
            <template #activator="{ props }">
              <VChip
                v-bind="props"
                class="px-3 font-weight-bold"
                color="info"
                text-color="white"
                size="default"
                prepend-icon="lucide:snowflake"
              >
                {{ kpi.pending_withdrawals || 0 }}
              </VChip>
            </template>
            <span>{{ t('dashboard.pending_withdrawals') }} · $ {{ fmtUsd(kpi.pending_withdrawals_usd) }}</span>
          </VTooltip>

          <VTooltip location="bottom">
            <template #activator="{ props }">
              <VChip
                v-bind="props"
                class="px-3 font-weight-bold"
                color="success"
                text-color="white"
                size="default"
              >
                $ {{ fmtUsd(kpi.traders_available) }}
              </VChip>
            </template>
            <span>{{ t('available_balance') }} ({{ t('tabs.traders_balance') }})</span>
          </VTooltip>

          <VTooltip location="bottom">
            <template #activator="{ props }">
              <VChip
                v-bind="props"
                class="px-3 font-weight-bold"
                color="info"
                text-color="white"
                size="default"
                prepend-icon="lucide:snowflake"
              >
                $ {{ fmtUsd(kpi.traders_frozen) }}
              </VChip>
            </template>
            <span>{{ t('frozen_balance') }} ({{ t('tabs.traders_balance') }})</span>
          </VTooltip>

          <VTooltip location="bottom">
            <template #activator="{ props }">
              <VChip
                v-bind="props"
                class="px-3 font-weight-bold"
                color="success"
                text-color="white"
                size="default"
              >
                $ {{ fmtUsd(kpi.merchants_available) }}
              </VChip>
            </template>
            <span>{{ t('available_balance') }} ({{ t('tabs.merchants_balance') }})</span>
          </VTooltip>
        </div>

        <div class="ui-dashboard__queues">
          <VChip
            v-for="item in queueItems"
            :key="item.key"
            :color="kpi[item.key] > 0 ? item.color : 'secondary'"
            variant="tonal"
            size="small"
            class="font-weight-medium"
          >
            {{ t(item.label) }}: {{ kpi[item.key] || 0 }}
          </VChip>
        </div>

        <section class="ui-dashboard__section">
          <h2 class="ui-dashboard__section-title">
            {{ t('dashboard.daily_turnover') }}
          </h2>
          <div class="ui-dashboard__chart">
            <VueApexCharts
              v-if="dailyChart.length"
              type="area"
              height="300"
              :series="turnoverChartSeries"
              :options="turnoverChartOptions"
            />
            <div
              v-else
              class="ui-data-table-empty"
            >
              {{ t('data.empty') }}
            </div>
          </div>
        </section>

        <section class="ui-dashboard__section">
          <h2 class="ui-dashboard__section-title">
            {{ t('dashboard.funnel_in') }} / {{ t('dashboard.funnel_out') }}
          </h2>
          <VRow dense>
            <VCol
              cols="12"
              md="6"
            >
              <div class="ui-dashboard__chart">
                <VueApexCharts
                  v-if="funnelIn.length"
                  type="bar"
                  height="260"
                  :series="funnelInChart.series"
                  :options="funnelInChart.options"
                />
                <div
                  v-else
                  class="ui-data-table-empty"
                >
                  {{ t('data.empty') }}
                </div>
              </div>
            </VCol>
            <VCol
              cols="12"
              md="6"
            >
              <div class="ui-dashboard__chart">
                <VueApexCharts
                  v-if="funnelOut.length"
                  type="bar"
                  height="260"
                  :series="funnelOutChart.series"
                  :options="funnelOutChart.options"
                />
                <div
                  v-else
                  class="ui-data-table-empty"
                >
                  {{ t('data.empty') }}
                </div>
              </div>
            </VCol>
          </VRow>
        </section>

        <section class="ui-dashboard__section">
          <h2 class="ui-dashboard__section-title">
            {{ t('dashboard.by_payment_system') }}
          </h2>
          <div
            v-if="byPaymentSystem.length"
            class="ui-dashboard__chart mb-3"
          >
            <VueApexCharts
              type="bar"
              height="260"
              :series="psChartSeries"
              :options="psChartOptions"
            />
          </div>
          <UiDataTable>
            <thead>
              <tr>
                <th scope="col">{{ t('payment_system') }}</th>
                <th scope="col">{{ t('currency') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.in_orders') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.in_completed') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.in_usd') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.out_orders') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.out_completed') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.out_usd') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.margin') }}</th>
                <th scope="col">{{ t('dashboard.conversion') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, index) in byPaymentSystem"
                :key="row.id"
                :class="{ 'ui-table-row--alt': index % 2 === 0 }"
              >
                <td class="ui-cell-primary">{{ row.name }}</td>
                <td>{{ row.currency || '—' }}</td>
                <td class="ui-data-table__cell--num">{{ row.in_count }}</td>
                <td class="ui-data-table__cell--num">{{ row.in_completed }}</td>
                <td class="ui-data-table__cell--num">
                  <span class="ui-cell-amount">{{ fmtUsd(row.in_completed_usd) }}</span>
                  <span class="ui-cell-currency">USD</span>
                </td>
                <td class="ui-data-table__cell--num">{{ row.out_count }}</td>
                <td class="ui-data-table__cell--num">{{ row.out_completed }}</td>
                <td class="ui-data-table__cell--num">
                  <span class="ui-cell-amount">{{ fmtUsd(row.out_completed_usd) }}</span>
                  <span class="ui-cell-currency">USD</span>
                </td>
                <td class="ui-data-table__cell--num">
                  <span class="ui-cell-amount">{{ fmtUsd(row.margin) }}</span>
                  <span class="ui-cell-currency">USD</span>
                </td>
                <td class="ui-cell-meta">
                  In {{ fmtPct(row.in_conversion) }} / Out {{ fmtPct(row.out_conversion) }}
                </td>
              </tr>
            </tbody>
            <tfoot v-show="!byPaymentSystem.length">
              <tr>
                <td
                  colspan="10"
                  class="text-center"
                >
                  <div class="ui-data-table-empty">{{ t('data.empty') }}</div>
                </td>
              </tr>
            </tfoot>
          </UiDataTable>
        </section>

        <section class="ui-dashboard__section">
          <h2 class="ui-dashboard__section-title">
            {{ t('dashboard.by_currency') }}
          </h2>
          <div
            v-if="byCurrency.length"
            class="ui-dashboard__chart mb-3"
          >
            <VueApexCharts
              type="bar"
              height="240"
              :series="currencyChartSeries"
              :options="currencyChartOptions"
            />
          </div>
          <UiDataTable>
            <thead>
              <tr>
                <th scope="col">{{ t('currency') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.in_orders') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.in_completed') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.in_usd') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.out_orders') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.out_completed') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.out_usd') }}</th>
                <th scope="col" class="text-end">{{ t('dashboard.margin') }}</th>
                <th scope="col">{{ t('dashboard.conversion') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, index) in byCurrency"
                :key="row.currency"
                :class="{ 'ui-table-row--alt': index % 2 === 0 }"
              >
                <td class="ui-cell-primary">{{ row.currency }}</td>
                <td class="ui-data-table__cell--num">{{ row.in_count }}</td>
                <td class="ui-data-table__cell--num">{{ row.in_completed }}</td>
                <td class="ui-data-table__cell--num">
                  <span class="ui-cell-amount">{{ fmtUsd(row.in_completed_usd) }}</span>
                  <span class="ui-cell-currency">USD</span>
                </td>
                <td class="ui-data-table__cell--num">{{ row.out_count }}</td>
                <td class="ui-data-table__cell--num">{{ row.out_completed }}</td>
                <td class="ui-data-table__cell--num">
                  <span class="ui-cell-amount">{{ fmtUsd(row.out_completed_usd) }}</span>
                  <span class="ui-cell-currency">USD</span>
                </td>
                <td class="ui-data-table__cell--num">
                  <span class="ui-cell-amount">{{ fmtUsd(row.margin) }}</span>
                  <span class="ui-cell-currency">USD</span>
                </td>
                <td class="ui-cell-meta">
                  In {{ fmtPct(row.in_conversion) }} / Out {{ fmtPct(row.out_conversion) }}
                </td>
              </tr>
            </tbody>
            <tfoot v-show="!byCurrency.length">
              <tr>
                <td
                  colspan="9"
                  class="text-center"
                >
                  <div class="ui-data-table-empty">{{ t('data.empty') }}</div>
                </td>
              </tr>
            </tfoot>
          </UiDataTable>
        </section>

        <section class="ui-dashboard__section">
          <h2 class="ui-dashboard__section-title">
            {{ t('tabs.exchange_rates') }}
          </h2>
          <UiDataTable>
            <thead>
              <tr>
                <th scope="col">{{ t('payment_system') }}</th>
                <th scope="col">{{ t('currency') }}</th>
                <th scope="col" class="text-end">{{ t('exchange_rate') }}</th>
                <th scope="col">{{ t('rate_source') }}</th>
                <th scope="col">{{ t('last_update') }}</th>
                <th scope="col">{{ t('in_on') }}</th>
                <th scope="col">{{ t('out_on') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(rate, index) in exchangeRates"
                :key="rate.id"
                :class="{ 'ui-table-row--alt': index % 2 === 0 }"
              >
                <td class="ui-cell-primary">{{ rate.name }}</td>
                <td>{{ rate.currency_symbol || '—' }}</td>
                <td class="ui-data-table__cell--num ui-cell-meta">
                  <template v-if="rate.currency_symbol">
                    1 USDT = {{ fmtUsd(rate.usdt_exchange_rate) }} {{ rate.currency_symbol }}
                  </template>
                  <template v-else>
                    {{ fmtUsd(rate.usdt_exchange_rate) }}
                  </template>
                </td>
                <td>{{ rate.rate_source || '—' }}</td>
                <td class="ui-data-table__cell--date">
                  {{ formatLastUpdate(rate.last_update) }}
                </td>
                <td>
                  <VChip
                    :color="rate.in_on ? 'success' : 'error'"
                    variant="tonal"
                    size="small"
                  >
                    {{ rate.in_on ? t('on') : t('off') }}
                  </VChip>
                </td>
                <td>
                  <VChip
                    :color="rate.out_on ? 'success' : 'error'"
                    variant="tonal"
                    size="small"
                  >
                    {{ rate.out_on ? t('on') : t('off') }}
                  </VChip>
                </td>
              </tr>
            </tbody>
            <tfoot v-show="!exchangeRates.length">
              <tr>
                <td
                  colspan="7"
                  class="text-center"
                >
                  <div class="ui-data-table-empty">{{ t('data.empty') }}</div>
                </td>
              </tr>
            </tfoot>
          </UiDataTable>
        </section>
      </template>
    </UiWorkspace>
  </div>
</template>
