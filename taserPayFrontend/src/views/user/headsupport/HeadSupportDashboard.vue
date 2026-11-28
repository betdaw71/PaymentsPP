<script setup>
import VueApexCharts from 'vue3-apexcharts'
import { useTheme } from 'vuetify'
import { useBaseStore } from '@/stores/useBaseStore'

const { t } = useI18n()
const theme = useTheme()
const baseStore = useBaseStore()

const snackbar = ref({
  enabled: false,
  type: 'error',
  message: '',
})

const empty = () => ({
  timezone: 'Europe/Moscow',
  preset: 'today',
  from: '',
  to: '',
  filters: { merchant: '', psp: '', ps: '', direction: 'both' },
  kpi: {
    turnover_usd: '0.00',
    net: '0.00',
    margin_pct: '0.00',
    orders_in: 0,
    orders_out: 0,
    conv_create_pct: '0.00',
    conv_issued_pct: '0.00',
    fx: '0.00',
  },
  daily: [],
  conversion: {
    created: 0,
    declined: 0,
    issued: 0,
    success: 0,
    create_to_success_pct: '0.00',
    issued_to_success_pct: '0.00',
  },
  pnl: {
    payin_mdr: '0.00',
    payin_fx: '0.00',
    payout_mdr: '0.00',
    trader_fee: '0.00',
    agent_fee: '0.00',
    expenses: '0.00',
    expense_count: 0,
    expenses_scoped: true,
    net: '0.00',
  },
  by_merchant: [],
  by_psp: [],
  filter_options: { merchants: [], psps: [], payment_systems: [] },
})

const data = ref(empty())
const loading = ref(false)

const filters = ref({
  preset: 'today',
  date_from: '',
  date_to: '',
  merchant: '',
  psp: '',
  ps: '',
  direction: 'both',
})

const moneyClass = value => {
  const n = Number(value)
  if (Number.isNaN(n) || n === 0) return ''
  return n > 0 ? 'text-success' : 'text-error'
}

const load = () => {
  loading.value = true
  const params = {
    preset: filters.value.preset,
    merchant: filters.value.merchant || undefined,
    psp: filters.value.psp || undefined,
    ps: filters.value.ps || undefined,
    direction: filters.value.direction || 'both',
  }
  if (filters.value.preset === 'custom') {
    params.date_from = filters.value.date_from || undefined
    params.date_to = filters.value.date_to || undefined
  }
  baseStore.getOpsDashboard(params).then(response => {
    if (response.error) throw response.error
    data.value = { ...empty(), ...response.data }
  }).catch(error => {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: error?.detail || error || 'error',
    }
  }).finally(() => {
    loading.value = false
  })
}

const resetFilters = () => {
  filters.value = {
    preset: 'today',
    date_from: '',
    date_to: '',
    merchant: '',
    psp: '',
    ps: '',
    direction: 'both',
  }
  load()
}

const applyMerchant = name => {
  filters.value.merchant = name === '(none)' ? '' : name
  load()
}

const applyPsp = name => {
  filters.value.psp = name === '(none)' ? '' : name
  load()
}

const chartSeries = computed(() => [
  {
    name: 'IN USD',
    data: (data.value.daily || []).map(d => Number(d.usd_in) || 0),
  },
  {
    name: 'OUT USD',
    data: (data.value.daily || []).map(d => Number(d.usd_out) || 0),
  },
])

const chartOptions = computed(() => {
  const primary = theme.current.value.colors.primary
  const secondary = theme.current.value.colors.secondary || '#8592a3'
  return {
    chart: {
      type: 'bar',
      stacked: false,
      toolbar: { show: false },
      fontFamily: 'inherit',
    },
    colors: [primary, secondary],
    plotOptions: {
      bar: {
        columnWidth: '55%',
        borderRadius: 4,
      },
    },
    dataLabels: { enabled: false },
    stroke: { show: true, width: 2, colors: ['transparent'] },
    xaxis: {
      categories: (data.value.daily || []).map(d => d.date.slice(5)),
      labels: { rotate: -45 },
    },
    yaxis: {
      labels: {
        formatter: v => Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }),
      },
      title: { text: 'USD' },
    },
    tooltip: {
      y: {
        formatter: v => `${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD`,
      },
    },
    legend: { position: 'top', horizontalAlign: 'left' },
    grid: { strokeDashArray: 4 },
  }
})

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
      <VCardTitle class="mt-2 ms-2 d-flex align-center flex-wrap ga-2">
        <VAvatar
          size="50"
          variant="text"
          color="primary"
          icon="tabler-chart-bar"
        />
        {{ t('tabs.ops_dashboard') }}
        <VSpacer />
        <VBtn
          icon="tabler-refresh"
          size="small"
          :loading="loading"
          @click="load"
        />
      </VCardTitle>

      <VCardText>
        <div class="text-medium-emphasis mb-4">
          {{ t('ops_dashboard.hint') }} · {{ data.timezone }}
          <span v-if="data.from">
            · {{ data.from.slice(0, 16) }} → {{ data.to.slice(0, 16) }}
          </span>
        </div>

        <!-- Filters -->
        <VRow dense class="mb-4">
          <VCol
            cols="12"
            sm="6"
            md="2"
          >
            <VSelect
              v-model="filters.preset"
              :items="[
                { title: t('ops_dashboard.preset_today'), value: 'today' },
                { title: t('ops_dashboard.preset_yesterday'), value: 'yesterday' },
                { title: t('ops_dashboard.preset_7d'), value: '7d' },
                { title: t('ops_dashboard.preset_month'), value: 'month' },
                { title: t('ops_dashboard.preset_custom'), value: 'custom' },
              ]"
              :label="t('ops_dashboard.period')"
              density="compact"
              hide-details
            />
          </VCol>
          <VCol
            v-if="filters.preset === 'custom'"
            cols="6"
            md="2"
          >
            <VTextField
              v-model="filters.date_from"
              type="date"
              :label="t('ops_dashboard.date_from')"
              density="compact"
              hide-details
            />
          </VCol>
          <VCol
            v-if="filters.preset === 'custom'"
            cols="6"
            md="2"
          >
            <VTextField
              v-model="filters.date_to"
              type="date"
              :label="t('ops_dashboard.date_to')"
              density="compact"
              hide-details
            />
          </VCol>
          <VCol
            cols="12"
            sm="6"
            md="2"
          >
            <VSelect
              v-model="filters.merchant"
              :items="[{ title: t('ops_dashboard.all'), value: '' }, ...(data.filter_options.merchants || []).map(m => ({ title: m, value: m }))]"
              :label="t('ops_dashboard.merchant')"
              density="compact"
              hide-details
              clearable
            />
          </VCol>
          <VCol
            cols="12"
            sm="6"
            md="2"
          >
            <VSelect
              v-model="filters.psp"
              :items="[{ title: t('ops_dashboard.all'), value: '' }, ...(data.filter_options.psps || []).map(m => ({ title: m, value: m }))]"
              :label="t('ops_dashboard.psp')"
              density="compact"
              hide-details
              clearable
            />
          </VCol>
          <VCol
            cols="12"
            sm="6"
            md="2"
          >
            <VSelect
              v-model="filters.ps"
              :items="[{ title: t('ops_dashboard.all'), value: '' }, ...(data.filter_options.payment_systems || []).map(m => ({ title: m, value: m }))]"
              :label="t('ops_dashboard.ps')"
              density="compact"
              hide-details
              clearable
            />
          </VCol>
          <VCol
            cols="12"
            sm="6"
            md="2"
          >
            <VSelect
              v-model="filters.direction"
              :items="[
                { title: t('ops_dashboard.dir_both'), value: 'both' },
                { title: t('ops_dashboard.dir_in'), value: 'in' },
                { title: t('ops_dashboard.dir_out'), value: 'out' },
              ]"
              :label="t('ops_dashboard.direction')"
              density="compact"
              hide-details
            />
          </VCol>
          <VCol
            cols="12"
            class="d-flex ga-2"
          >
            <VBtn
              color="primary"
              :loading="loading"
              @click="load"
            >
              {{ t('ops_dashboard.apply') }}
            </VBtn>
            <VBtn
              variant="tonal"
              @click="resetFilters"
            >
              {{ t('ops_dashboard.reset') }}
            </VBtn>
          </VCol>
        </VRow>

        <!-- KPI -->
        <VRow>
          <VCol
            cols="12"
            sm="6"
            md="4"
            lg="2"
          >
            <VCard variant="outlined">
              <VCardText>
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.kpi_turnover') }}
                </div>
                <div class="text-h6 font-weight-medium">
                  {{ data.kpi.turnover_usd }} USDT
                </div>
              </VCardText>
            </VCard>
          </VCol>
          <VCol
            cols="12"
            sm="6"
            md="4"
            lg="2"
          >
            <VCard variant="outlined">
              <VCardText>
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.kpi_net') }}
                </div>
                <div
                  class="text-h6 font-weight-medium"
                  :class="moneyClass(data.kpi.net)"
                >
                  {{ data.kpi.net }} USDT
                </div>
                <div class="text-caption">
                  {{ data.kpi.margin_pct }}%
                </div>
              </VCardText>
            </VCard>
          </VCol>
          <VCol
            cols="12"
            sm="6"
            md="4"
            lg="2"
          >
            <VCard variant="outlined">
              <VCardText>
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.kpi_orders') }}
                </div>
                <div class="text-h6 font-weight-medium">
                  {{ data.kpi.orders_in }} in / {{ data.kpi.orders_out }} out
                </div>
              </VCardText>
            </VCard>
          </VCol>
          <VCol
            cols="12"
            sm="6"
            md="4"
            lg="2"
          >
            <VCard variant="outlined">
              <VCardText>
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.kpi_conv_create') }}
                </div>
                <div class="text-h6 font-weight-medium">
                  {{ data.kpi.conv_create_pct }}%
                </div>
              </VCardText>
            </VCard>
          </VCol>
          <VCol
            cols="12"
            sm="6"
            md="4"
            lg="2"
          >
            <VCard variant="outlined">
              <VCardText>
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.kpi_conv_issued') }}
                </div>
                <div class="text-h6 font-weight-medium">
                  {{ data.kpi.conv_issued_pct }}%
                </div>
              </VCardText>
            </VCard>
          </VCol>
          <VCol
            cols="12"
            sm="6"
            md="4"
            lg="2"
          >
            <VCard variant="outlined">
              <VCardText>
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.kpi_fx') }}
                </div>
                <div
                  class="text-h6 font-weight-medium"
                  :class="moneyClass(data.kpi.fx)"
                >
                  {{ data.kpi.fx }} USDT
                </div>
              </VCardText>
            </VCard>
          </VCol>
        </VRow>

        <!-- Volume chart -->
        <VCard
          class="mt-4"
          variant="outlined"
        >
          <VCardTitle class="text-body-1">
            {{ t('ops_dashboard.volume_chart') }}
          </VCardTitle>
          <VCardText>
            <VueApexCharts
              type="bar"
              height="320"
              :series="chartSeries"
              :options="chartOptions"
            />
          </VCardText>
        </VCard>

        <!-- Conversion under chart -->
        <VCard
          class="mt-4"
          variant="outlined"
        >
          <VCardTitle class="text-body-1">
            {{ t('ops_dashboard.conversion') }}
          </VCardTitle>
          <VCardText>
            <VRow>
              <VCol
                cols="6"
                md="2"
              >
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.conv_created') }}
                </div>
                <div class="text-h6">
                  {{ data.conversion.created }}
                </div>
              </VCol>
              <VCol
                cols="6"
                md="2"
              >
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.conv_declined') }}
                </div>
                <div class="text-h6">
                  {{ data.conversion.declined }}
                </div>
              </VCol>
              <VCol
                cols="6"
                md="2"
              >
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.conv_issued') }}
                </div>
                <div class="text-h6">
                  {{ data.conversion.issued }}
                </div>
              </VCol>
              <VCol
                cols="6"
                md="2"
              >
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.conv_success') }}
                </div>
                <div class="text-h6">
                  {{ data.conversion.success }}
                </div>
              </VCol>
              <VCol
                cols="6"
                md="2"
              >
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.kpi_conv_create') }}
                </div>
                <div class="text-h6">
                  {{ data.conversion.create_to_success_pct }}%
                </div>
              </VCol>
              <VCol
                cols="6"
                md="2"
              >
                <div class="text-caption text-medium-emphasis">
                  {{ t('ops_dashboard.kpi_conv_issued') }}
                </div>
                <div class="text-h6">
                  {{ data.conversion.issued_to_success_pct }}%
                </div>
              </VCol>
            </VRow>
          </VCardText>
        </VCard>

        <!-- PnL + tables -->
        <VRow class="mt-2">
          <VCol
            cols="12"
            md="4"
          >
            <VCard variant="outlined">
              <VCardTitle class="text-body-1">
                {{ t('ops_dashboard.pnl') }}
              </VCardTitle>
              <VCardText>
                <VTable density="compact">
                  <tbody>
                    <tr>
                      <td>{{ t('cash_register.payin_mdr') }}</td>
                      <td class="text-end">
                        {{ data.pnl.payin_mdr }}
                      </td>
                    </tr>
                    <tr>
                      <td>{{ t('cash_register.payin_fx') }}</td>
                      <td class="text-end">
                        {{ data.pnl.payin_fx }}
                      </td>
                    </tr>
                    <tr>
                      <td>{{ t('cash_register.payout_mdr') }}</td>
                      <td class="text-end">
                        {{ data.pnl.payout_mdr }}
                      </td>
                    </tr>
                    <tr>
                      <td>{{ t('cash_register.trader_fee') }}</td>
                      <td class="text-end">
                        −{{ data.pnl.trader_fee }}
                      </td>
                    </tr>
                    <tr>
                      <td>{{ t('cash_register.agent_fee') }}</td>
                      <td class="text-end">
                        −{{ data.pnl.agent_fee }}
                      </td>
                    </tr>
                    <tr>
                      <td>
                        {{ t('cash_register.expenses') }}
                        <span
                          v-if="!data.pnl.expenses_scoped"
                          class="text-caption text-medium-emphasis"
                        >({{ t('ops_dashboard.expenses_hidden') }})</span>
                      </td>
                      <td class="text-end">
                        −{{ data.pnl.expenses }}
                      </td>
                    </tr>
                    <tr>
                      <td class="font-weight-medium">
                        {{ t('cash_register.net') }}
                      </td>
                      <td
                        class="text-end font-weight-medium"
                        :class="moneyClass(data.pnl.net)"
                      >
                        {{ data.pnl.net }}
                      </td>
                    </tr>
                  </tbody>
                </VTable>
              </VCardText>
            </VCard>
          </VCol>

          <VCol
            cols="12"
            md="8"
          >
            <VCard variant="outlined">
              <VCardTitle class="text-body-1">
                {{ t('ops_dashboard.by_merchant') }}
              </VCardTitle>
              <VCardText class="overflow-x-auto">
                <VTable density="compact">
                  <thead>
                    <tr>
                      <th>{{ t('ops_dashboard.merchant') }}</th>
                      <th class="text-end">
                        n
                      </th>
                      <th class="text-end">
                        USD
                      </th>
                      <th class="text-end">
                        MDR
                      </th>
                      <th class="text-end">
                        FX
                      </th>
                      <th class="text-end">
                        PSP
                      </th>
                      <th class="text-end">
                        NET
                      </th>
                      <th class="text-end">
                        %
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="row in data.by_merchant"
                      :key="row.name"
                      style="cursor: pointer"
                      @click="applyMerchant(row.name)"
                    >
                      <td>{{ row.name }}</td>
                      <td class="text-end">
                        {{ row.n }}
                      </td>
                      <td class="text-end">
                        {{ row.usd }}
                      </td>
                      <td class="text-end">
                        {{ row.mdr }}
                      </td>
                      <td class="text-end">
                        {{ row.fx }}
                      </td>
                      <td class="text-end">
                        {{ row.trader_fee }}
                      </td>
                      <td
                        class="text-end"
                        :class="moneyClass(row.net)"
                      >
                        {{ row.net }}
                      </td>
                      <td class="text-end">
                        {{ row.margin_pct }}
                      </td>
                    </tr>
                  </tbody>
                </VTable>
              </VCardText>
            </VCard>
          </VCol>
        </VRow>

        <VCard
          class="mt-4"
          variant="outlined"
        >
          <VCardTitle class="text-body-1">
            {{ t('ops_dashboard.by_psp') }}
          </VCardTitle>
          <VCardText class="overflow-x-auto">
            <VTable density="compact">
              <thead>
                <tr>
                  <th>{{ t('ops_dashboard.psp') }}</th>
                  <th class="text-end">
                    n
                  </th>
                  <th class="text-end">
                    USD
                  </th>
                  <th class="text-end">
                    MDR
                  </th>
                  <th class="text-end">
                    FX
                  </th>
                  <th class="text-end">
                    PSP fee
                  </th>
                  <th class="text-end">
                    NET
                  </th>
                  <th class="text-end">
                    margin%
                  </th>
                  <th class="text-end">
                    eff cost%
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in data.by_psp"
                  :key="row.name"
                  style="cursor: pointer"
                  @click="applyPsp(row.name)"
                >
                  <td>{{ row.name }}</td>
                  <td class="text-end">
                    {{ row.n }}
                  </td>
                  <td class="text-end">
                    {{ row.usd }}
                  </td>
                  <td class="text-end">
                    {{ row.mdr }}
                  </td>
                  <td class="text-end">
                    {{ row.fx }}
                  </td>
                  <td class="text-end">
                    {{ row.trader_fee }}
                  </td>
                  <td
                    class="text-end"
                    :class="moneyClass(row.net)"
                  >
                    {{ row.net }}
                  </td>
                  <td class="text-end">
                    {{ row.margin_pct }}
                  </td>
                  <td class="text-end">
                    {{ row.eff_psp_cost_pct }}
                  </td>
                </tr>
              </tbody>
            </VTable>
          </VCardText>
        </VCard>
      </VCardText>
    </VCard>
  </div>
</template>
