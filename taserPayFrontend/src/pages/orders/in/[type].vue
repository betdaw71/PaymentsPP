<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { useTradeStore } from "@/stores/useTradeStore"
import {
  capitalize,
  formatUUID,
  resolveOrderInStatusVariantAndIcon,
  formatTimeDelta, formatTimeDeltaSeconds,
  formatDeltaTimeVariantAndIcon, resolveOrderInStatus,
} from "@core/utils/formatters"
import { useBaseStore } from "@/stores/useBaseStore"
import OrderInDrawer from "@/views/user/OrderInDrawer.vue"
import TeamLeadOrderScopeToggle from "@/components/teamlead/TeamLeadOrderScopeToggle.vue"
import { onUnmounted } from "vue"

const props = defineProps ({
  type: {
    type: String,
    required: false,
    default: "all",
  },
})


const { t } = useI18n ()
const tradeStore = useTradeStore ()
const authStore = useAuthStore ()
const baseStore = useBaseStore ()

const router = useRouter()
const route = useRoute()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const filterOptions = ref ({
  currencies: [],
  merchants: [],
  payment_system: [],
  traffic_type: [],
  status: [],
  teams: [],
  traders: [],
})

const currentPage = ref (1)
const totalPage = ref (1)
const total = ref (0)
const items = ref ([])
const selectedRows = ref ([])
const autoUpdateInterval = ref (null)
const autoUpdateStartTimestamp = ref (null)
const nowTime = ref (Date.now ())
const timeInterval = ref (null)
const isOrderInDrawerOpen = ref (false)
const totalUSDAmount = ref (0)
const totalComission = ref (0)
const holdAmount = ref (0)
const currentType = ref (structuredClone (toRaw (props.type)))

watch (props, () => {
  currentType.value = structuredClone (toRaw (props.type))
})

console.log ({ nowTime: nowTime.value })


const filters = ref (
  structuredClone (toRaw (baseStore.orders_in_filters)),
)

const isTeamleadMerchantScope = computed(
  () => authStore.is_team_lead() && filters.value.teamleadScope === 'merchant',
)

watch(
  () => filters.value.teamleadScope,
  () => {
    if (authStore.is_team_lead())
      getOrders(true)
  },
)

const copyToClipboard = (valueToCopy, alertMessage, alertType = "error") => {
  navigator.clipboard.writeText (valueToCopy)
    .then (() => {
      snackbar.value = {
        enabled: true,
        type: alertType,
        message: alertMessage,
      }
    })
    .catch (error => {
      console.error ('Failed to copy to clipboard: ', error)
      snackbar.value = {
        enabled: true,
        type: "error",
        message: `Error occurred: ${error}`,
      }
    })
}

const loadMessage = ref ({
  message: t ('data.loading'),
  status: 0,
})

const orderingTypes = [
  {
    value: "-creation_date",
    name: "Date (Desc)",
  },
  {
    value: "creation_date",
    name: "Date (Asc)",
  },
  {
    value: "-amount",
    name: "Amount (Desc)",
  },
  {
    value: "amount",
    name: "Amount (Asc)",
  },
  {
    value: "-usd_amount",
    name: "USD Amount (Desc)",
  },
  {
    value: "usd_amount",
    name: "USD Amount (Asc)",
  },
  {
    value: "-status",
    name: "Status (Desc)",
  },
  {
    value: "status",
    name: "Status (Asc)",
  },
  {
    value: "-completion_time",
    name: "Completion (Desc)",
  },
  {
    value: "completion_time",
    name: "Completion (Asc)",
  },
]

const autoUpdateModes = [
  { value: 0, name: "Off" },
  { value: 10, name: "10s" },
  { value: 20, name: "20s" },
  { value: 30, name: "30s" },
  { value: 60, name: "1m" },
]

const rowsPerPageOptions = [
  { value: 10, name: "x10" },
  { value: 20, name: "x20" },
  { value: 50, name: "x50" },
]

const autoUpdateProgress = computed (
  () => {
    if (!autoUpdateStartTimestamp.value)
      return 0
    const now = nowTime.value
    const diff = now - autoUpdateStartTimestamp.value

    return 100 - Math.round (diff / (filters.value.autoUpdateMode * 1000) * 100)
  },
)

const autoUpdateProgressSeconds = computed (
  () => {
    return Math.max (
      Math.min (
        Math.round (autoUpdateProgress.value * filters.value.autoUpdateMode / 100),
        filters.value.autoUpdateMode,
      ),
      0)
  },
)

const getFiltersOrder = async () => {
  tradeStore.getFiltersOrderIn ({}).then (
    response => {
      if (response.error)
        throw response.error
      filterOptions.value = response.data
    },
    error => {
      snackbar.value = {
        enabled: true,
        type: "error",
        message: error,
      }
    },
  )
}

const getOrders = async (resetInterval = false) => {
  loadMessage.value = {
    message: t ('data.loading'),
    status: 0,
  }
  items.value = []
  if (resetInterval) {
    clearInterval (autoUpdateInterval.value)
    if (filters.value.autoUpdateMode) {
      autoUpdateInterval.value = setInterval (() => {
        console.log ('inside getOrders')
        getOrders ()
      }, filters.value.autoUpdateMode * 1000)
    }
  }
  autoUpdateStartTimestamp.value = filters.value.autoUpdateMode ? Date.now () : null

  const params = {
    per_page: filters.value.rowsPerPage,
    page: currentPage.value,
  }

  console.log ({ params })


  // Base Filters
  if (filters.value.ordering)
    params.ordering = filters.value.ordering
  // Filters always apply (Variant A — no apply_filters toggle)
  if (filters.value.searchQueryId)
    params.id = filters.value.searchQueryId
  if (filters.value.selectedStatus && filters.value.selectedStatus.length > 0)
    params.status__name__in = filters.value.selectedStatus.join (",")
  if (filters.value.selectedPaymentSystems && filters.value.selectedPaymentSystems.length > 0)
    params.payment_system__name__in = filters.value.selectedPaymentSystems.join (",")
  if (filters.value.minAmount)
    params.amount__gte = filters.value.minAmount
  if (filters.value.maxAmount)
    params.amount__lte = filters.value.maxAmount
  if (filters.value.minUSDAmount)
    params.usd_amount__gte = filters.value.minUSDAmount
  if (filters.value.maxUSDAmount)
    params.usd_amount__lte = filters.value.maxUSDAmount
  if (filters.value.dateRange && filters.value.dateRange.includes (" to "))
    params.creation_date__range = filters.value.dateRange.replace (" to ", ",").replaceAll (" ", "T")

  if (filters.value.selectedCurrencies && filters.value.selectedCurrencies.length > 0)
    params.currency__symbol__in = filters.value.selectedCurrencies.join (",")
  if (filters.value.searchMerchantOrderId)
    params.merchant_order_id = filters.value.searchMerchantOrderId

  if (filters.value.selectedTrafficTypes && filters.value.selectedTrafficTypes.length > 0)
    params.traffic_type__name__in = filters.value.selectedTrafficTypes.join (",")
  if (filters.value.searchPaymentDetailsId)
    params.payment_details__id = filters.value.searchPaymentDetailsId
  if (filters.value.searchTransactionId)
    params.transaction_id = filters.value.searchTransactionId
  if (filters.value.searchPaymentDetailsGroupId)
    params.payment_details__group__id = filters.value.searchPaymentDetailsGroupId
  if (filters.value.searchPaymentDetailsGroupOwner)
    params.payment_details__group__owner__icontains = filters.value.searchPaymentDetailsGroupOwner
  if (filters.value.searchCustomerId)
    params.customer_id = filters.value.searchCustomerId

  if (filters.value.selectedTraders && filters.value.selectedTraders.length > 0)
    params.trader__user__username__in = filters.value.selectedTraders.join (",")

  if (filters.value.selectedTeams && filters.value.selectedTeams.length > 0)
    params.trader__team__name__in = filters.value.selectedTeams.join (",")

  if (filters.value.selectedMerchants && filters.value.selectedMerchants.length > 0)
    params.merchant__user__username__in = filters.value.selectedMerchants.join (",")

  if (authStore.is_team_lead() && filters.value.teamleadScope === 'merchant')
    params.scope = 'merchant'

  tradeStore.getTradeOrderIn (params).then (response => {
    if (response.error) {
      throw response.error
    }
    console.log ({ response })
    items.value = response.data.results
    total.value = response.data.count
    totalUSDAmount.value = response.data.total_usd_amount
    totalComission.value = response.data.total_commission
    holdAmount.value = response.data.hold
    totalPage.value = parseInt (total.value / filters.value.rowsPerPage) + (total.value % filters.value.rowsPerPage === 0 ? 0 : 1) || 1
    if (items.value.length === 0) {
      loadMessage.value = {
        message: t ('data.empty'),
        status: 2,
      }
    }
  }).catch (error => {
    console.log (error)
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
  })
}

watch(
  () => currentType.value,
  () => {
    const resolvedStatuses = resolveOrderInStatus (currentType.value)

    console.log ({ resolvedStatuses, type: currentType.value })
    if (resolvedStatuses !== null) {
      filters.value.selectedStatus = resolvedStatuses
    }
    getOrders ()
  },
  { immediate: true },
)

onMounted (
  () => {
    if (route.query.teamlead_scope === 'merchant') {
      filters.value.teamleadScope = 'merchant'
      baseStore.orders_in_filters.teamleadScope = 'merchant'
      baseStore.orders_out_filters.teamleadScope = 'merchant'
    }
    timeInterval.value = setInterval (() => {
      nowTime.value = Date.now ()
    }, 1000)
    getOrders ()
    if (filters.value.autoUpdateMode > 0) {
      autoUpdateInterval.value = setInterval (() => {
        getOrders ()
      }, filters.value.autoUpdateMode * 1000)
    }

    getFiltersOrder ()
  },
)

watchEffect (() => {
  if (currentPage.value > totalPage.value)
    currentPage.value = totalPage.value
})

watch (
  () => {
    return {
      currentPage: currentPage.value,
      rowsPerPage: filters.value.rowsPerPage,
    }
  },
  () => {
    getOrders ()
  },
  { deep: true },
)


const paginationData = computed (() => {
  const firstIndex = items.value.length ? (currentPage.value - 1) * filters.value.rowsPerPage + 1 : 0
  const lastIndex = items.value.length + (currentPage.value - 1) * filters.value.rowsPerPage

  return `${t ('pagination.showing')} ${firstIndex} ${t ('pagination.to')} ${lastIndex} ${t ('pagination.of')} ${total.value} ${t ('pagination.entries')}`
})

watch (
  () => filters.value,
  () => {
    baseStore.orders_in_filters = structuredClone (toRaw (filters.value))
  },
  { deep: true },
)
watch (
  () => filters.value.autoUpdateMode,
  () => {
    console.log ({
      _: filters.value.autoUpdateMode,
    })
    if (autoUpdateInterval.value) {
      clearInterval (autoUpdateInterval.value)
    }
    if (filters.value.autoUpdateMode) {
      getOrders ()
      autoUpdateInterval.value = setInterval (() => {
        getOrders ()
      }, filters.value.autoUpdateMode * 1000)
    }
  },
  { deep: true },
)

const switchSelection = (values, name, key) => {
  if (filters.value[name].length !== 0) {
    filters.value[name] = []
  } else {
    filters.value[name] = JSON.parse (JSON.stringify (values.map (item => item[key])))
  }
}

const orderItemId = ref (null)

const openOrderDetails = item => {
  orderItemId.value = item.id
  isOrderInDrawerOpen.value = true
}

onBeforeUnmount (
  () => {
    if (timeInterval.value)
      clearInterval (timeInterval.value)
    if (autoUpdateInterval.value)
      clearInterval (autoUpdateInterval.value)

  },
)

const exportLoading = ref(false)

const filterPanelExpanded = ref(false)

const countAdvancedFilters = f => {
  let n = 0
  if (f.searchCustomerId) n++
  if (f.searchPaymentDetailsGroupId) n++
  if (f.searchPaymentDetailsGroupOwner) n++
  if (f.searchPaymentDetailsId) n++
  if (f.searchTransactionId) n++
  if (currentType.value === 'all' && f.selectedStatus?.length) n++
  if (f.selectedPaymentSystems?.length) n++
  if (f.selectedMerchants?.length) n++
  if (f.selectedCurrencies?.length) n++
  if (f.selectedTrafficTypes?.length) n++
  if (f.selectedTraders?.length) n++
  if (f.selectedTeams?.length) n++
  if (f.dateRange) n++
  if (f.minAmount) n++
  if (f.maxAmount) n++
  if (f.minUSDAmount) n++
  if (f.maxUSDAmount) n++
  if (f.ordering && f.ordering !== '-creation_date') n++
  return n
}

const advancedFilterCount = computed(() => countAdvancedFilters(filters.value))

const activeFilterChips = computed(() => {
  const chips = []
  const f = filters.value

  if (currentType.value !== 'all') {
    chips.push({
      key: 'navStatus',
      label: `${t('status')}: ${t(`order_status.${currentType.value.toLowerCase()}`)}`,
    })
  }

  if (f.searchQueryId)
    chips.push({ key: 'searchQueryId', label: `ID: ${f.searchQueryId}` })
  if (f.searchMerchantOrderId)
    chips.push({ key: 'searchMerchantOrderId', label: `${t('merchant_order_id')}: ${f.searchMerchantOrderId}` })
  if (f.searchCustomerId)
    chips.push({ key: 'searchCustomerId', label: `${t('customer_id')}: ${f.searchCustomerId}` })
  if (f.searchPaymentDetailsGroupId)
    chips.push({ key: 'searchPaymentDetailsGroupId', label: `${t('payment_details_group_id')}: ${f.searchPaymentDetailsGroupId}` })
  if (f.searchPaymentDetailsGroupOwner)
    chips.push({ key: 'searchPaymentDetailsGroupOwner', label: `${t('payment_details_group_owner')}: ${f.searchPaymentDetailsGroupOwner}` })
  if (f.searchPaymentDetailsId)
    chips.push({ key: 'searchPaymentDetailsId', label: `${t('payment_details_id')}: ${f.searchPaymentDetailsId}` })
  if (f.searchTransactionId)
    chips.push({ key: 'searchTransactionId', label: `${t('transaction_id')}: ${f.searchTransactionId}` })

  if (currentType.value === 'all') {
    f.selectedStatus?.forEach(status => {
      chips.push({
        key: `status:${status}`,
        label: `${t('status')}: ${t(`order_status.${status.toLowerCase()}`)}`,
      })
    })
  }

  f.selectedPaymentSystems?.forEach(ps => {
    chips.push({ key: `ps:${ps}`, label: `${t('payment_system')}: ${ps}` })
  })
  f.selectedCurrencies?.forEach(c => {
    chips.push({ key: `currency:${c}`, label: `${t('currencies')}: ${c}` })
  })
  f.selectedTrafficTypes?.forEach(tt => {
    chips.push({ key: `traffic:${tt}`, label: `${t('traffic_types')}: ${tt}` })
  })
  f.selectedTraders?.forEach(tr => {
    chips.push({ key: `trader:${tr}`, label: `${t('traders')}: ${tr}` })
  })
  f.selectedTeams?.forEach(team => {
    chips.push({ key: `team:${team}`, label: `${t('teams')}: ${team}` })
  })
  f.selectedMerchants?.forEach(m => {
    chips.push({ key: `merchant:${m}`, label: `${t('merchants')}: ${m}` })
  })

  if (f.dateRange)
    chips.push({ key: 'dateRange', label: `${t('creation_date_range')}: ${f.dateRange}` })
  if (f.minAmount)
    chips.push({ key: 'minAmount', label: `${t('min_amount_fiat')}: ${f.minAmount}` })
  if (f.maxAmount)
    chips.push({ key: 'maxAmount', label: `${t('max_amount_fiat')}: ${f.maxAmount}` })
  if (f.minUSDAmount)
    chips.push({ key: 'minUSDAmount', label: `${t('min_amount_usdt')}: ${f.minUSDAmount}` })
  if (f.maxUSDAmount)
    chips.push({ key: 'maxUSDAmount', label: `${t('max_amount_usdt')}: ${f.maxUSDAmount}` })
  if (f.ordering && f.ordering !== '-creation_date') {
    const orderingLabel = orderingTypes.find(o => o.value === f.ordering)?.name ?? f.ordering
    chips.push({ key: 'ordering', label: `${t('ordering')}: ${orderingLabel}` })
  }

  return chips
})

const removeFilterChip = key => {
  if (key === 'navStatus') {
    router.push('/orders/in/all')
    return
  }

  const f = filters.value
  const scalarKeys = {
    searchQueryId: '',
    searchMerchantOrderId: '',
    searchCustomerId: '',
    searchPaymentDetailsGroupId: '',
    searchPaymentDetailsGroupOwner: '',
    searchPaymentDetailsId: '',
    searchTransactionId: '',
    dateRange: '',
    minAmount: 0,
    maxAmount: 0,
    minUSDAmount: 0,
    maxUSDAmount: 0,
    ordering: '-creation_date',
  }

  if (key in scalarKeys) {
    f[key] = scalarKeys[key]
  } else if (key.startsWith('status:')) {
    const status = key.slice(7)
    f.selectedStatus = f.selectedStatus.filter(s => s !== status)
  } else if (key.startsWith('ps:')) {
    f.selectedPaymentSystems = f.selectedPaymentSystems.filter(s => s !== key.slice(3))
  } else if (key.startsWith('currency:')) {
    f.selectedCurrencies = f.selectedCurrencies.filter(s => s !== key.slice(9))
  } else if (key.startsWith('traffic:')) {
    f.selectedTrafficTypes = f.selectedTrafficTypes.filter(s => s !== key.slice(8))
  } else if (key.startsWith('trader:')) {
    f.selectedTraders = f.selectedTraders.filter(s => s !== key.slice(7))
  } else if (key.startsWith('team:')) {
    f.selectedTeams = f.selectedTeams.filter(s => s !== key.slice(5))
  } else if (key.startsWith('merchant:')) {
    f.selectedMerchants = f.selectedMerchants.filter(s => s !== key.slice(9))
  }

  getOrders(true)
}

const toggleFilterPanel = () => {
  filterPanelExpanded.value = !filterPanelExpanded.value
}

const searchOrders = () => {
  getOrders(true)
}

const resetFilters = () => {
  const { rowsPerPage, autoUpdateMode } = filters.value
  filters.value = {
    searchQueryId: '',
    rowsPerPage,
    searchPaymentDetailsGroupId: '',
    searchPaymentDetailsGroupOwner: '',
    searchCustomerId: '',
    selectedStatus: [],
    selectedPaymentSystems: [],
    selectedMerchants: [],
    selectedCurrencies: [],
    selectedTrafficTypes: [],
    selectedTraders: [],
    selectedTeams: [],
    searchMerchantOrderId: '',
    searchPaymentDetailsId: '',
    searchTransactionId: '',
    minAmount: 0,
    maxAmount: 0,
    minUSDAmount: 0,
    maxUSDAmount: 0,
    dateRange: '',
    ordering: '-creation_date',
    autoUpdateMode,
  }
  const resolvedStatuses = resolveOrderInStatus(currentType.value)
  if (resolvedStatuses !== null)
    filters.value.selectedStatus = resolvedStatuses
  getOrders(true)
}

const exportOrders = async () => {
  exportLoading.value = true
  tradeStore.exportTradeOrderIn ({}).then (
    response => {
      exportLoading.value = false
      if (response.error)
        throw response.error
      snackbar.value = {
        enabled: true,
        type: "success",
        message: t ('data.exported'),
      }
    },
    error => {
      exportLoading.value = false
      snackbar.value = {
        enabled: true,
        type: "error",
        message: error,
      }
    },
  )
}
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
    <UiWorkspace v-if="authStore.is_authenticated()">
      <template #header>
        <div class="ui-workspace__title-row">
          <VAvatar
            size="40"
            variant="text"
            color="primary"
            icon="lucide:arrow-down-left"
          />
          <h1 class="ui-workspace__title">
            {{ t('tabs.orders_in') }}
          </h1>
        </div>
        <TeamLeadOrderScopeToggle class="mt-2" />
      </template>
      <template #actions>
        <UiButton
          variant="default"
          size="small"
          :loading="exportLoading"
          @click="exportOrders"
        >
          <VIcon
            icon="lucide:share"
            size="16"
            start
          />
          {{ $t('export') }}
        </UiButton>
        <UiRefreshControl
          :interval="filters.autoUpdateMode"
          :progress="autoUpdateProgress"
          :progress-seconds="autoUpdateProgressSeconds"
          :items="autoUpdateModes"
          @refresh="getOrders(true)"
          @update:interval="filters.autoUpdateMode = $event"
        />
      </template>

      <!-- Search + filters zone (single wrapper) -->
      <div class="ui-orders-filter-zone">
                <div class="ui-orders-search">
                  <div class="ui-orders-search__field">
                    <AppTextField
                      v-model="filters.searchQueryId"
                      :label="$t('id')"
                      placeholder="22652802379"
                      density="compact"
                      class="ui-field--mono"
                      @keydown.enter="searchOrders"
                    />
                  </div>
                  <div
                    v-if="(authStore.is_merchant() && !authStore.is_team_lead()) || authStore.is_support() || authStore.is_head_of_support()"
                    class="ui-orders-search__field"
                  >
                    <AppTextField
                      v-model="filters.searchMerchantOrderId"
                      :label="$t('merchant_order_id')"
                      density="compact"
                      @keydown.enter="searchOrders"
                    />
                  </div>
                  <UiButton
                    variant="default"
                    size="small"
                    @click="toggleFilterPanel"
                  >
                    <VIcon
                      icon="lucide:filter"
                      size="16"
                      start
                    />
                    {{ $t('filters') }}
                    <span
                      v-if="advancedFilterCount > 0"
                      class="ui-filter-panel__badge ms-1"
                    >
                      {{ advancedFilterCount }}
                    </span>
                  </UiButton>
                  <UiButton
                    variant="primary"
                    size="small"
                    @click="searchOrders"
                  >
                    <VIcon
                      icon="lucide:search"
                      size="16"
                      start
                    />
                    {{ $t('search') }}
                  </UiButton>
                </div>

                <UiFilterChips
                  :chips="activeFilterChips"
                  :clear-label="$t('clear_all_filters')"
                  @remove="removeFilterChip"
                  @clear-all="resetFilters"
                />

                <UiFilterPanel
                  v-model:expanded="filterPanelExpanded"
                  :active-count="advancedFilterCount"
                  :title="$t('advanced_filters')"
                  embedded
                  @apply="searchOrders"
                  @reset="resetFilters"
                >
                  <UiFilterSection :title="$t('filter_section_identifiers')">
                    <VRow dense>
                      <VCol
                        v-if="!authStore.is_trader() && !authStore.is_team_lead()"
                        cols="12"
                        sm="6"
                        md="4"
                      >
                        <AppTextField
                          v-model="filters.searchCustomerId"
                          :label="$t('customer_id')"
                          density="compact"
                        />
                      </VCol>
                      <VCol
                        v-if="!authStore.is_merchant()"
                        cols="12"
                        sm="6"
                        md="4"
                      >
                        <AppTextField
                          v-model="filters.searchPaymentDetailsGroupId"
                          :label="$t('payment_details_group_id')"
                          density="compact"
                        />
                      </VCol>
                      <VCol
                        v-if="!authStore.is_merchant()"
                        cols="12"
                        sm="6"
                        md="4"
                      >
                        <AppTextField
                          v-model="filters.searchPaymentDetailsGroupOwner"
                          :label="$t('payment_details_group_owner')"
                          density="compact"
                        />
                      </VCol>
                    </VRow>
                  </UiFilterSection>

                  <UiFilterSection :title="$t('filter_section_status')">
                    <VRow dense>
                      <VCol
                        v-if="currentType === 'all'"
                        cols="12"
                        sm="6"
                        md="4"
                      >
                        <AppSelect
                          v-model="filters.selectedStatus"
                          :label="$t('status')"
                          :items="filterOptions.status"
                          :item-title="option => $t (`order_status.${option.name.toLowerCase()}`)"
                          item-value="name"
                          multiple
                          clearable
                          clear-icon="lucide:x"
                          :prepend-inner-icon="filters.selectedStatus.length === filterOptions.status.length ? 'lucide:square-check': 'lucide:square'"
                          @click:prependInner="switchSelection(filterOptions.status, 'selectedStatus', 'name')"
                        />
                      </VCol>
                      <VCol
                        cols="12"
                        sm="6"
                        md="4"
                      >
                        <AppSelect
                          v-model="filters.selectedPaymentSystems"
                          :label="$t('payment_systems')"
                          :items="filterOptions.payment_system"
                          item-title="name"
                          item-value="name"
                          multiple
                          clearable
                          clear-icon="lucide:x"
                          :prepend-inner-icon="filters.selectedPaymentSystems.length === filterOptions.payment_system.length ? 'lucide:square-check': 'lucide:square'"
                          @click:prependInner="switchSelection(filterOptions.payment_system, 'selectedPaymentSystems', 'name')"
                        />
                      </VCol>
                    </VRow>
                  </UiFilterSection>

                  <UiFilterSection :title="$t('filter_section_amounts')">
                    <VRow dense>
                      <VCol
                        cols="12"
                        sm="6"
                        md="4"
                      >
                        <AppDateTimePicker
                          v-model="filters.dateRange"
                          :label="$t('creation_date_range')"
                          :config="{ mode: 'range', enableTime: true, dateFormat: 'Y-m-d H:i'}"
                          clearable
                          clear-icon="lucide:x"
                        />
                      </VCol>
                      <VCol
                        cols="12"
                        sm="6"
                        md="2"
                      >
                        <AppTextField
                          v-model="filters.minAmount"
                          :label="$t('min_amount_fiat')"
                          type="number"
                          clearable
                          clear-icon="lucide:x"
                        />
                      </VCol>
                      <VCol
                        cols="12"
                        sm="6"
                        md="2"
                      >
                        <AppTextField
                          v-model="filters.maxAmount"
                          :label="$t('max_amount_fiat')"
                          type="number"
                          clearable
                          clear-icon="lucide:x"
                        />
                      </VCol>
                      <VCol
                        cols="12"
                        sm="6"
                        md="2"
                      >
                        <AppTextField
                          v-model="filters.minUSDAmount"
                          :label="$t('min_amount_usdt')"
                          type="number"
                          clearable
                          clear-icon="lucide:x"
                        />
                      </VCol>
                      <VCol
                        cols="12"
                        sm="6"
                        md="2"
                      >
                        <AppTextField
                          v-model="filters.maxUSDAmount"
                          :label="$t('max_amount_usdt')"
                          type="number"
                          clearable
                          clear-icon="lucide:x"
                        />
                      </VCol>
                      <VCol
                        cols="12"
                        sm="6"
                        md="4"
                      >
                        <AppSelect
                          v-model="filters.ordering"
                          :label="$t('ordering')"
                          :items="orderingTypes"
                          :item-title="option => $t (`orderings.${option.value.toLowerCase()}`)"
                          item-value="value"
                          clear-icon="lucide:x"
                        />
                      </VCol>
                    </VRow>
                  </UiFilterSection>

                  <UiFilterSection
                    v-if="authStore.is_merchant() || authStore.is_head_of_support() || authStore.is_support() || authStore.is_senior_trader() || authStore.is_trader()"
                    :title="$t('filter_section_people')"
                  >
                    <template v-if="authStore.is_merchant()">
                        <VRow dense>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedCurrencies"
                              :label="$t('currencies')"
                              :items="filterOptions.currencies"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedCurrencies.length === filterOptions.currencies.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.currencies, 'selectedCurrencies', 'name')"
                            />
                          </VCol>
                          <VCol
                            v-if="authStore.is_team_lead()"
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTraders"
                              :label="$t('traders')"
                              :items="filterOptions.traders"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTraders.length === filterOptions.traders.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.traders, 'selectedTraders', 'name')"
                            />
                          </VCol>
                          <VCol
                            v-if="authStore.is_team_lead()"
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTeams"
                              :label="$t('teams')"
                              :items="filterOptions.teams"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTeams.length === filterOptions.teams.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.teams, 'selectedTeams', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppTextField
                              v-model="filters.searchTransactionId"
                              :label="$t('transaction_id')"
                            />
                          </VCol>
                        </VRow>
                      </template>
                      <template
                        v-else-if="authStore.is_head_of_support()"
                      >
                        <VRow>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedCurrencies"
                              :label="$t('currencies')"
                              :items="filterOptions.currencies"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedCurrencies.length === filterOptions.currencies.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.currencies, 'selectedCurrencies', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTrafficTypes"
                              :label="$t('traffic_types')"
                              :items="filterOptions.traffic_type"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTrafficTypes.length === filterOptions.traffic_type.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.traffic_type, 'selectedTrafficTypes', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppTextField
                              v-model="filters.searchPaymentDetailsId"
                              :label="$t('payment_details_id')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppTextField
                              v-model="filters.searchTransactionId"
                              :label="$t('transaction_id')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTraders"
                              :label="$t('traders')"
                              :items="filterOptions.traders"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTraders.length === filterOptions.traders.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.traders, 'selectedTraders', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTeams"
                              :label="$t('teams')"
                              :items="filterOptions.teams"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTeams.length === filterOptions.teams.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.teams, 'selectedTeams', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedMerchants"
                              :label="$t('merchants')"
                              :items="filterOptions.merchants"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedMerchants.length === filterOptions.merchants.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.merchants, 'selectedMerchants', 'name')"
                            />
                          </VCol>
                        </VRow>
                      </template>
                      <template
                        v-else-if="authStore.is_support()"
                      >
                        <VRow>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedCurrencies"
                              :label="$t('currencies')"
                              :items="filterOptions.currencies"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedCurrencies.length === filterOptions.currencies.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.currencies, 'selectedCurrencies', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTrafficTypes"
                              :label="$t('traffic_types')"
                              :items="filterOptions.traffic_type"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTrafficTypes.length === filterOptions.traffic_type.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.traffic_type, 'selectedTrafficTypes', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppTextField
                              v-model="filters.searchPaymentDetailsId"
                              :label="$t('payment_details_id')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppTextField
                              v-model="filters.searchTransactionId"
                              :label="$t('transaction_id')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTraders"
                              :label="$t('traders')"
                              :items="filterOptions.traders"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTraders.length === filterOptions.traders.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.traders, 'selectedTraders', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTeams"
                              :label="$t('teams')"
                              :items="filterOptions.teams"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTeams.length === filterOptions.teams.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.teams, 'selectedTeams', 'name')"
                            />
                          </VCol>
                        </VRow>
                      </template>
                      <template
                        v-else-if="authStore.is_senior_trader()"
                      >
                        <VRow>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTrafficTypes"
                              :label="$t('traffic_types')"
                              :items="filterOptions.traffic_type"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTrafficTypes.length === filterOptions.traffic_type.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.traffic_type, 'selectedTrafficTypes', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppTextField
                              v-model="filters.searchPaymentDetailsId"
                              :label="$t('payment_details_id')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppTextField
                              v-model="filters.searchTransactionId"
                              :label="$t('transaction_id')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTraders"
                              :label="$t('traders')"
                              :items="filterOptions.traders"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTraders.length === filterOptions.traders.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.traders, 'selectedTraders', 'name')"
                            />
                          </VCol>
                        </VRow>
                      </template>
                      <template
                        v-else-if="authStore.is_trader()"
                      >
                        <VRow>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppSelect
                              v-model="filters.selectedTrafficTypes"
                              :label="$t('traffic_types')"
                              :items="filterOptions.traffic_type"
                              item-title="name"
                              item-value="name"
                              multiple
                              clearable
                              clear-icon="lucide:x"
                              :prepend-inner-icon="filters.selectedTrafficTypes.length === filterOptions.traffic_type.length ? 'lucide:square-check': 'lucide:square'"
                              @click:prepend-inner="switchSelection(filterOptions.traffic_type, 'selectedTrafficTypes', 'name')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppTextField
                              v-model="filters.searchPaymentDetailsId"
                              :label="$t('payment_details_id')"
                            />
                          </VCol>
                          <VCol
                            cols="12"
                            sm="4"
                            md="3"
                            lg="2"
                          >
                            <AppTextField
                              v-model="filters.searchTransactionId"
                              :label="$t('transaction_id')"
                            />
                          </VCol>
                        </VRow>
                      </template>
                  </UiFilterSection>
                </UiFilterPanel>
              </div>

              <!-- Summary for current result set (above table) -->
              <div class="ui-orders-metrics ui-orders-metrics--above-table">
                <div class="ui-metric-inline">
                  <div class="ui-metric-inline__item ui-metric-inline__item--accent">
                    <span class="ui-metric-inline__label">{{ $t('total_usd_amount') }}</span>
                    <span class="ui-metric-inline__value">${{ totalUSDAmount }}</span>
                  </div>
                  <div class="ui-metric-inline__item ui-metric-inline__item--accent">
                    <span class="ui-metric-inline__label">{{ $t('total_commission') }}</span>
                    <span class="ui-metric-inline__value">${{ totalComission }}</span>
                  </div>
                  <div class="ui-metric-inline__item ui-metric-inline__item--info">
                    <span class="ui-metric-inline__label">{{ $t('hold') }}</span>
                    <span class="ui-metric-inline__value ui-metric-inline__value--with-icon">
                      <VIcon
                        v-if="!isTeamleadMerchantScope"
                        icon="lucide:snowflake"
                        size="16"
                        color="info"
                      />
                      {{ isTeamleadMerchantScope ? '—' : holdAmount }}
                    </span>
                  </div>
                </div>
              </div>

              <!-- SECTION Table -->
              <UiDataTable :loading="loadMessage.status === 0">
                <thead>
                  <tr>
                    <th scope="col">
                      {{ $t('status') }} / {{ $t('completion_time') }}
                    </th>
                    <th scope="col">
                      {{ $t('expires') }}
                    </th>
                    <th scope="col" class="text-end">
                      {{ $t('amount') }}
                    </th>
                    <th scope="col" class="text-end">
                      {{ $t('usd_amount') }}
                    </th>
                    <th scope="col">
                      {{ $t('payment_system') }}
                    </th>
                    <th
                      v-if="isTeamleadMerchantScope"
                      scope="col"
                    >
                      {{ $t('merchant') }}
                    </th>
                    <th
                      v-if="isTeamleadMerchantScope"
                      scope="col"
                      class="text-end"
                    >
                      {{ $t('merchant_agent.agent_fee') }}
                    </th>
                    <th
                      v-if="isTeamleadMerchantScope"
                      scope="col"
                    >
                      {{ $t('merchant_order_id') }}
                    </th>
                    <th
                      v-if="authStore.is_support() || authStore.is_trader()"
                      scope="col"
                    >
                      {{ $t('payment_details') }}
                    </th>
                    <th scope="col">
                      {{ $t('id') }}
                    </th>
                    <!--                    <th -->
                    <!--                      v-if="authStore.is_support() || authStore.is_trader()" -->
                    <!--                      scope="col" -->
                    <!--                    > -->
                    <!--                      {{ $t('traffic_type') }} -->
                    <!--                    </th> -->
                    <th
                      v-if="authStore.is_support() || authStore.is_senior_trader()"
                      scope="col"
                    >
                      {{ $t('trader') }}
                    </th>
                    <th
                      v-if="authStore.is_head_of_support()"
                      scope="col"
                    >
                      {{ $t('merchant') }}
                    </th>
                    <th
                      v-if="(authStore.is_head_of_support() || authStore.is_merchant()) && !authStore.is_team_lead()"
                      scope="col"
                    >
                      {{ $t('merchant_order_id') }}
                    </th>
                    <th scope="col">
                      {{ $t('date') }}
                    </th>
                  </tr>
                </thead>

                <tbody>
                  <tr
                    v-for="(item, index) in items"
                    :key="item.id"
                    class="cursor-pointer"
                    :class="{
                      'ui-table-row--selected': item.id === orderItemId && isOrderInDrawerOpen,
                      'ui-table-row--alt': index % 2 === 0,
                    }"
                    @click="openOrderDetails (item)"
                  >
                    <td class="ui-data-table__cell--status">
                      <div class="ui-cell-stack">
                        <div class="d-flex align-center gap-1">
                          <VChip
                            size="small"
                            :color="resolveOrderInStatusVariantAndIcon(item.status).variant"
                            variant="tonal"
                            :prepend-icon="resolveOrderInStatusVariantAndIcon(item.status).icon"
                          >
                            {{ resolveOrderInStatusVariantAndIcon(item.status).text }}
                          </VChip>
                          <VTooltip
                            v-if="!authStore.is_merchant() && item.auto_closed"
                            location="right"
                          >
                            <template #activator="{ props }">
                              <VIcon
                                v-bind="props"
                                color="error"
                                icon="lucide:bot"
                                size="16"
                              />
                            </template>
                            <span>{{ $t ('auto_closed') }}</span>
                          </VTooltip>
                        </div>
                        <span class="ui-cell-meta">
                          <template v-if="item.status === 'New'">
                            {{ formatTimeDeltaSeconds (nowTime, parseInt (item.expires_at) * 1000) }}
                          </template>
                          <template v-else>
                            {{
                              item.completion_date ? formatTimeDeltaSeconds (parseInt (item.creation_date) * 1000, parseInt (item.completion_date) * 1000) : $t('not_completed')
                            }}
                          </template>
                        </span>
                      </div>
                    </td>
                    <td v-if="['Money sent by user'].includes(item.status)">
                      <VChip
                            size="small"
                            :color="formatDeltaTimeVariantAndIcon(parseInt(item.expires_at) * 1000 - nowTime).variant"
                            variant="tonal"
                            :prepend-icon="formatDeltaTimeVariantAndIcon(parseInt(item.expires_at) * 1000 - nowTime).icon"
                          >
                            {{ formatDeltaTimeVariantAndIcon(parseInt(item.expires_at) * 1000 - nowTime).text }}
                          </VChip>
                    </td>
                    <td v-else>
                      <span class="ui-cell-meta">{{ $t ('no_data') }}</span>
                    </td>
                    <td class="ui-data-table__cell--num">
                      <span class="ui-cell-amount">{{ item.amount }}</span>
                      <span class="ui-cell-currency">{{ item.currency }}</span>
                    </td>
                    <td class="ui-data-table__cell--num">
                      <span class="ui-cell-amount">{{ item.usd_amount }}</span>
                      <span class="ui-cell-currency">USD</span>
                    </td>
                    <td class="ui-cell-primary">
                      {{ item.payment_system }}
                    </td>
                    <td v-if="isTeamleadMerchantScope">
                      @{{ item.merchant_username }}
                    </td>
                    <td
                      v-if="isTeamleadMerchantScope"
                      class="ui-data-table__cell--num"
                    >
                      {{ item.agent_fee }}
                    </td>
                    <td v-if="isTeamleadMerchantScope">
                      {{ item.merchant_order_id }}
                    </td>
                    <td
                      v-if="authStore.is_support() || authStore.is_trader()"
                    >
                      <span
                        v-for="(detail, name) in item.payment_details"
                        :key="name"
                      >
                        {{ $t(`fields.${name}`) }} : <span class="font-weight-bold">{{ detail }}</span> <br>
                      </span>
                    </td>
                    <td>
                      <VTooltip location="top">
                        <template #activator="{ props }">
                          <button
                            type="button"
                            class="ui-copy-id"
                            v-bind="props"
                            @click.stop="copyToClipboard (item.id, 'Order ID copied!', 'success')"
                          >
                            {{ formatUUID (item.id) }}
                          </button>
                        </template>
                        <span>{{ item.id }}</span>
                      </VTooltip>
                    </td>
                    <!--                    <td -->
                    <!--                      v-if="authStore.is_support() || authStore.is_trader()" -->
                    <!--                    > -->
                    <!--                      {{ item.traffic_type }} -->
                    <!--                    </td> -->
                    <td
                      v-if="authStore.is_support() || authStore.is_senior_trader()"
                    >
                      <VChip
                        color="alternative"
                        text-color="white"
                        small
                      >
                        @{{ item.trader }}
                      </VChip>
                    </td>
                    <td
                      v-if="authStore.is_head_of_support()"
                    >
                      <VChip
                        color="alternative"
                        text-color="white"
                        small
                      >
                        @{{ item.merchant }}
                      </VChip>
                    </td>
                    <td
                      v-if="(authStore.is_head_of_support() || authStore.is_merchant()) && !authStore.is_team_lead()"
                    >
                      <VTooltip location="top">
                        <template #activator="{ props }">
                          <button
                            type="button"
                            class="ui-copy-id"
                            v-bind="props"
                            @click.stop="copyToClipboard (item.merchant_order_id, 'Merchant Order ID copied!', 'success')"
                          >
                            {{ item.merchant_order_id }}
                          </button>
                        </template>
                        <span>{{ item.merchant_order_id }}</span>
                      </VTooltip>
                    </td>
                    <!--                    <td> -->
                    <!--                      <VTooltip -->
                    <!--                        v-if="item.transaction_id" -->
                    <!--                        location="top" -->
                    <!--                      > -->
                    <!--                        <template #activator="{ props }"> -->
                    <!--                          <VBtn -->
                    <!--                            size="small" -->
                    <!--                            variant="text" -->
                    <!--                            class="text-lowercase" -->
                    <!--                            v-bind="props" -->
                    <!--                            @click.stop="copyToClipboard (item.transaction_id, 'Transaction ID copied!', 'success')" -->
                    <!--                          > -->
                    <!--                            {{ item.transaction_id }} -->
                    <!--                          </VBtn> -->
                    <!--                        </template> -->
                    <!--                        <span> -->
                    <!--                          {{ item.transaction_id }} -->
                    <!--                        </span> -->
                    <!--                      </VTooltip> -->
                    <!--                    </td> -->
                    <!--                    <td -->
                    <!--                      v-if="authStore.is_support()" -->
                    <!--                    > -->
                    <!--                      {{ item.client_ip }} -->
                    <!--                    </td> -->
                    <td class="ui-data-table__cell--date">
                      {{ (new Date (parseInt (item.creation_date) * 1000)).toUTCString () }}
                      <VTooltip activator="parent">
                        <p class="mb-0">
                          {{ $t ('created_at') }}: {{ (new Date (parseInt (item.creation_date) * 1000)).toUTCString () }}
                        </p>
                      </VTooltip>
                    </td>
                  </tr>
                </tbody>

                <!-- 👉 table footer  -->

                <tfoot v-show="!items || !items.length">
                  <tr>
                    <td
                      colspan="12"
                      class="text-center"
                    >
                      <div class="ui-data-table-empty">
                        <span>{{ loadMessage.message }}</span>
                        <VProgressCircular
                          v-if="loadMessage.status === 0"
                          :width="3"
                          size="20"
                          color="primary"
                          indeterminate
                        />
                        <VIcon
                          v-else-if="loadMessage.status === 1"
                          color="success"
                          icon="lucide:check"
                          size="20"
                        />
                        <VIcon
                          v-else
                          color="error"
                          icon="lucide:x"
                          size="20"
                        />
                      </div>
                    </td>
                  </tr>
                </tfoot>
              </UiDataTable>

              <template #footer>
                <div class="ui-orders-footer">
                  <span class="text-sm text-disabled">{{ paginationData }}</span>
                  <div class="d-flex align-center gap-4">
                    <div class="ui-orders-footer__rows">
                      <VSelect
                        v-model="filters.rowsPerPage"
                        :items="rowsPerPageOptions"
                        :label="$t('rows')"
                        item-title="name"
                        item-value="value"
                        density="compact"
                        hide-details
                        scroll-strategy="close"
                        color="primary"
                      />
                    </div>
                    <VPagination
                      v-model="currentPage"
                      size="small"
                      :total-visible="5"
                      :length="totalPage"
                      @next="selectedRows = []"
                      @prev="selectedRows = []"
                    />
                  </div>
                </div>
              </template>
    </UiWorkspace>

    <OrderInDrawer
      v-if="authStore.is_authenticated()"
      v-model:isDrawerOpen="isOrderInDrawerOpen"
      v-model:order-id="orderItemId"
      v-model:time="nowTime"
    />
  </div>
</template>
