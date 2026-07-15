<script setup>
import VueApexCharts from 'vue3-apexcharts'
import { useTheme } from 'vuetify'
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

const periodItems = computed (() => [
  { title: t ('dashboard.period_day'), value: 'day' },
  { title: t ('dashboard.period_7d'), value: '7d' },
  { title: t ('dashboard.period_30d'), value: '30d' },
])

const paymentSystemItems = computed (() => {
  const all = { title: t ('dashboard.all_payment_systems'), value: null }
  const items = (dashboard.value?.filters?.payment_systems || []).map (
    ps => ({
      title: `${ps.name} (${ps.currency || '?'})`,
      value: ps.id,
    }),
  )

  return [all, ...items]
})

const currencyItems = computed (() => {
  const all = { title: t ('dashboard.all_currencies'), value: null }
  const items = (dashboard.value?.filters?.currencies || []).map (
    c => ({ title: c.symbol, value: c.symbol }),
  )

  return [all, ...items]
})

const fmtUsd = v => {
  if (v === null || v === undefined) {
    return '0'
  }

  return Number (v).toLocaleString (undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

const fmtPct = v => `${Number (v || 0).toFixed (1)}%`

const kpi = computed (() => dashboard.value?.kpi || {})
const funnelIn = computed (() => dashboard.value?.funnel_in || [])
const funnelOut = computed (() => dashboard.value?.funnel_out || [])
const dailyChart = computed (() => dashboard.value?.daily_chart || [])
const byPaymentSystem = computed (() => dashboard.value?.by_payment_system || [])
const byCurrency = computed (() => dashboard.value?.by_currency || [])
const exchangeRates = computed (() => dashboard.value?.exchange_rates || [])

const chartTheme = computed (() => {
  const colors = vuetifyTheme.current.value.colors

  return {
    primary: colors.primary,
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
    info: colors.info,
  }
})

const turnoverChartSeries = computed (() => [
  {
    name: t ('dashboard.turnover_in'),
    data: dailyChart.value.map (d => d.in_usd),
  },
  {
    name: t ('dashboard.turnover_out'),
    data: dailyChart.value.map (d => d.out_usd),
  },
  {
    name: t ('dashboard.margin'),
    data: dailyChart.value.map (d => d.margin),
  },
])

const turnoverChartOptions = computed (() => ({
  chart: {
    type: 'area',
    toolbar: { show: false },
    parentHeightOffset: 0,
  },
  stroke: { curve: 'smooth', width: 2 },
  dataLabels: { enabled: false },
  colors: [chartTheme.value.success, chartTheme.value.info, chartTheme.value.warning],
  xaxis: {
    categories: dailyChart.value.map (d => d.date),
    labels: { rotate: -45 },
  },
  yaxis: {
    labels: {
      formatter: val => `$${Math.round (val)}`,
    },
  },
  legend: { position: 'top' },
  fill: {
    type: 'gradient',
    gradient: { opacityFrom: 0.4, opacityTo: 0.05 },
  },
}))

const makeFunnelChart = (title, data) => ({
  series: [{
    name: t ('dashboard.orders'),
    data: data.map (row => row.count),
  }],
  options: {
    chart: { type: 'bar', toolbar: { show: false } },
    plotOptions: {
      bar: { horizontal: true, borderRadius: 4 },
    },
    dataLabels: { enabled: true },
    colors: [chartTheme.value.primary],
    xaxis: {
      categories: data.map (row => row.status),
    },
    title: { text: title, align: 'left', style: { fontSize: '14px' } },
  },
})

const funnelInChart = computed (() => makeFunnelChart (t ('dashboard.funnel_in'), funnelIn.value))
const funnelOutChart = computed (() => makeFunnelChart (t ('dashboard.funnel_out'), funnelOut.value))

const psChartSeries = computed (() => [
  {
    name: t ('dashboard.turnover_in'),
    data: byPaymentSystem.value.map (r => r.in_completed_usd),
  },
  {
    name: t ('dashboard.turnover_out'),
    data: byPaymentSystem.value.map (r => r.out_completed_usd),
  },
])

const psChartOptions = computed (() => ({
  chart: { type: 'bar', toolbar: { show: false }, stacked: false },
  plotOptions: { bar: { borderRadius: 4, columnWidth: '55%' } },
  colors: [chartTheme.value.success, chartTheme.value.info],
  xaxis: {
    categories: byPaymentSystem.value.map (
      r => `${r.name} (${r.currency || '?'})`,
    ),
    labels: { rotate: -25 },
  },
  yaxis: {
    labels: { formatter: val => `$${Math.round (val)}` },
  },
  legend: { position: 'top' },
}))

const currencyChartSeries = computed (() => [
  {
    name: t ('dashboard.turnover_in'),
    data: byCurrency.value.map (r => r.in_completed_usd),
  },
  {
    name: t ('dashboard.turnover_out'),
    data: byCurrency.value.map (r => r.out_completed_usd),
  },
])

const currencyChartOptions = computed (() => ({
  chart: { type: 'bar', toolbar: { show: false } },
  plotOptions: { bar: { borderRadius: 4 } },
  colors: [chartTheme.value.success, chartTheme.value.info],
  xaxis: { categories: byCurrency.value.map (r => r.currency) },
  yaxis: {
    labels: { formatter: val => `$${Math.round (val)}` },
  },
  legend: { position: 'top' },
}))

const fetchDashboard = () => {
  loading.value = true
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

    <!-- Filters -->
    <VCard class="mb-4">
      <VCardText class="d-flex flex-wrap align-center gap-4">
        <VSelect
          v-model="period"
          :items="periodItems"
          :label="$t('dashboard.period')"
          density="compact"
          style="min-width: 140px;"
          hide-details
        />
        <VSelect
          v-model="paymentSystem"
          :items="paymentSystemItems"
          :label="$t('payment_system')"
          density="compact"
          style="min-width: 220px;"
          hide-details
          clearable
        />
        <VSelect
          v-model="currency"
          :items="currencyItems"
          :label="$t('currency')"
          density="compact"
          style="min-width: 140px;"
          hide-details
          clearable
        />
        <VSpacer />
        <VBtn
          icon="tabler-refresh"
          variant="tonal"
          :loading="loading"
          @click="fetchDashboard"
        />
      </VCardText>
    </VCard>

    <div v-if="loading && !dashboard">
      <VProgressLinear indeterminate color="primary" />
    </div>

    <template v-else-if="dashboard">
      <!-- KPI -->
      <VRow class="mb-4">
        <VCol
          cols="12"
          sm="6"
          md="3"
        >
          <VCard>
            <VCardText>
              <div class="text-caption text-medium-emphasis">
                {{ $t('dashboard.turnover_in') }}
              </div>
              <div class="text-h5">
                ${{ fmtUsd(kpi.in_turnover_usd) }}
              </div>
              <div class="text-caption">
                {{ kpi.in_completed }} / {{ kpi.in_created }} · {{ fmtPct(kpi.in_conversion) }}
              </div>
            </VCardText>
          </VCard>
        </VCol>
        <VCol
          cols="12"
          sm="6"
          md="3"
        >
          <VCard>
            <VCardText>
              <div class="text-caption text-medium-emphasis">
                {{ $t('dashboard.turnover_out') }}
              </div>
              <div class="text-h5">
                ${{ fmtUsd(kpi.out_turnover_usd) }}
              </div>
              <div class="text-caption">
                {{ kpi.out_completed }} / {{ kpi.out_created }} · {{ fmtPct(kpi.out_conversion) }}
              </div>
            </VCardText>
          </VCard>
        </VCol>
        <VCol
          cols="12"
          sm="6"
          md="3"
        >
          <VCard>
            <VCardText>
              <div class="text-caption text-medium-emphasis">
                {{ $t('dashboard.margin') }}
              </div>
              <div class="text-h5 text-success">
                ${{ fmtUsd(kpi.margin_usd) }}
              </div>
            </VCardText>
          </VCard>
        </VCol>
        <VCol
          cols="12"
          sm="6"
          md="3"
        >
          <VCard>
            <VCardText>
              <div class="text-caption text-medium-emphasis">
                {{ $t('dashboard.pending_withdrawals') }}
              </div>
              <div class="text-h5 text-warning">
                {{ kpi.pending_withdrawals }}
              </div>
              <div class="text-caption">
                ${{ fmtUsd(kpi.pending_withdrawals_usd) }}
              </div>
            </VCardText>
          </VCard>
        </VCol>
      </VRow>

      <!-- Queues -->
      <VRow class="mb-4">
        <VCol
          v-for="item in [
            { key: 'manual_check_out', label: 'dashboard.manual_check', color: 'warning' },
            { key: 'arbitrage_in', label: 'dashboard.arbitrage_in', color: 'error' },
            { key: 'arbitrage_out', label: 'dashboard.arbitrage_out', color: 'error' },
            { key: 'cannot_process_in', label: 'dashboard.cannot_process_in', color: 'error' },
            { key: 'cannot_process_out', label: 'dashboard.cannot_process_out', color: 'error' },
          ]"
          :key="item.key"
          cols="6"
          sm="4"
          md="2"
        >
          <VChip
            :color="kpi[item.key] > 0 ? item.color : 'default'"
            variant="tonal"
            class="w-100 justify-center pa-4"
            label
          >
            {{ $t(item.label) }}: {{ kpi[item.key] || 0 }}
          </VChip>
        </VCol>
      </VRow>

      <!-- Balances -->
      <VRow class="mb-4">
        <VCol
          cols="12"
          md="6"
        >
          <VCard>
            <VCardTitle>{{ $t('tabs.traders_balance') }}</VCardTitle>
            <VCardText class="d-flex gap-6">
              <div>
                <div class="text-caption">
                  {{ $t('available_balance') }}
                </div>
                <div class="text-h6">
                  ${{ fmtUsd(kpi.traders_available) }}
                </div>
              </div>
              <div>
                <div class="text-caption">
                  {{ $t('frozen_balance') }}
                </div>
                <div class="text-h6">
                  ${{ fmtUsd(kpi.traders_frozen) }}
                </div>
              </div>
            </VCardText>
          </VCard>
        </VCol>
        <VCol
          cols="12"
          md="6"
        >
          <VCard>
            <VCardTitle>{{ $t('tabs.merchants_balance') }}</VCardTitle>
            <VCardText class="d-flex gap-6">
              <div>
                <div class="text-caption">
                  {{ $t('available_balance') }}
                </div>
                <div class="text-h6">
                  ${{ fmtUsd(kpi.merchants_available) }}
                </div>
              </div>
              <div>
                <div class="text-caption">
                  {{ $t('frozen_balance') }}
                </div>
                <div class="text-h6">
                  ${{ fmtUsd(kpi.merchants_frozen) }}
                </div>
              </div>
            </VCardText>
          </VCard>
        </VCol>
      </VRow>

      <!-- Daily chart -->
      <VCard class="mb-4">
        <VCardTitle>{{ $t('dashboard.daily_turnover') }}</VCardTitle>
        <VCardText>
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
            {{ $t('data.empty') }}
          </div>
        </VCardText>
      </VCard>

      <!-- Funnels -->
      <VRow class="mb-4">
        <VCol
          cols="12"
          md="6"
        >
          <VCard>
            <VCardText>
              <VueApexCharts
                v-if="funnelIn.length"
                type="bar"
                height="280"
                :series="funnelInChart.series"
                :options="funnelInChart.options"
              />
            </VCardText>
          </VCard>
        </VCol>
        <VCol
          cols="12"
          md="6"
        >
          <VCard>
            <VCardText>
              <VueApexCharts
                v-if="funnelOut.length"
                type="bar"
                height="280"
                :series="funnelOutChart.series"
                :options="funnelOutChart.options"
              />
            </VCardText>
          </VCard>
        </VCol>
      </VRow>

      <!-- By payment system -->
      <VCard class="mb-4">
        <VCardTitle>{{ $t('dashboard.by_payment_system') }}</VCardTitle>
        <VCardText>
          <VueApexCharts
            v-if="byPaymentSystem.length"
            type="bar"
            height="300"
            :series="psChartSeries"
            :options="psChartOptions"
            class="mb-4"
          />
          <VTable class="text-no-wrap">
            <thead>
              <tr>
                <th>{{ $t('payment_system') }}</th>
                <th>{{ $t('currency') }}</th>
                <th>{{ $t('dashboard.in_orders') }}</th>
                <th>{{ $t('dashboard.in_completed') }}</th>
                <th>{{ $t('dashboard.in_usd') }}</th>
                <th>{{ $t('dashboard.out_orders') }}</th>
                <th>{{ $t('dashboard.out_completed') }}</th>
                <th>{{ $t('dashboard.out_usd') }}</th>
                <th>{{ $t('dashboard.margin') }}</th>
                <th>{{ $t('dashboard.conversion') }}</th>
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
                <td>${{ fmtUsd(row.in_completed_usd) }}</td>
                <td>{{ row.out_count }}</td>
                <td>{{ row.out_completed }}</td>
                <td>${{ fmtUsd(row.out_completed_usd) }}</td>
                <td>${{ fmtUsd(row.margin) }}</td>
                <td>In {{ fmtPct(row.in_conversion) }} / Out {{ fmtPct(row.out_conversion) }}</td>
              </tr>
            </tbody>
          </VTable>
        </VCardText>
      </VCard>

      <!-- By currency -->
      <VCard class="mb-4">
        <VCardTitle>{{ $t('dashboard.by_currency') }}</VCardTitle>
        <VCardText>
          <VueApexCharts
            v-if="byCurrency.length"
            type="bar"
            height="260"
            :series="currencyChartSeries"
            :options="currencyChartOptions"
            class="mb-4"
          />
          <VTable class="text-no-wrap">
            <thead>
              <tr>
                <th>{{ $t('currency') }}</th>
                <th>{{ $t('dashboard.in_orders') }}</th>
                <th>{{ $t('dashboard.in_completed') }}</th>
                <th>{{ $t('dashboard.in_usd') }}</th>
                <th>{{ $t('dashboard.out_orders') }}</th>
                <th>{{ $t('dashboard.out_completed') }}</th>
                <th>{{ $t('dashboard.out_usd') }}</th>
                <th>{{ $t('dashboard.margin') }}</th>
                <th>{{ $t('dashboard.conversion') }}</th>
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
                <td>${{ fmtUsd(row.in_completed_usd) }}</td>
                <td>{{ row.out_count }}</td>
                <td>{{ row.out_completed }}</td>
                <td>${{ fmtUsd(row.out_completed_usd) }}</td>
                <td>${{ fmtUsd(row.margin) }}</td>
                <td>In {{ fmtPct(row.in_conversion) }} / Out {{ fmtPct(row.out_conversion) }}</td>
              </tr>
            </tbody>
          </VTable>
        </VCardText>
      </VCard>

      <!-- Exchange rates compact -->
      <VCard>
        <VCardTitle>{{ $t('tabs.exchange_rates') }}</VCardTitle>
        <VCardText>
          <VTable class="text-no-wrap">
            <thead>
              <tr>
                <th>{{ $t('payment_system') }}</th>
                <th>{{ $t('currency') }}</th>
                <th>{{ $t('exchange_rate') }}</th>
                <th>{{ $t('rate_source') }}</th>
                <th>In</th>
                <th>Out</th>
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
                </td>
                <td>{{ rate.rate_source || '—' }}</td>
                <td>
                  <VChip
                    :color="rate.in_on ? 'success' : 'error'"
                    size="x-small"
                    label
                  >
                    {{ rate.in_on ? $t('on') : $t('off') }}
                  </VChip>
                </td>
                <td>
                  <VChip
                    :color="rate.out_on ? 'success' : 'error'"
                    size="x-small"
                    label
                  >
                    {{ rate.out_on ? $t('on') : $t('off') }}
                  </VChip>
                </td>
              </tr>
            </tbody>
          </VTable>
        </VCardText>
      </VCard>
    </template>
  </div>
</template>
