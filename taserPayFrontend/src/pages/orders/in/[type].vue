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
  if (filters.value.apply_filters) {
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


    // Merchant Filters
    if (filters.value.selectedCurrencies && filters.value.selectedCurrencies.length > 0)
      params.currency__symbol__in = filters.value.selectedCurrencies.join (",")
    if (filters.value.searchMerchantOrderId)
      params.merchant_order_id = filters.value.searchMerchantOrderId

    // Trader Filters

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

    // Trader Boss Filters (Only)
    if (filters.value.selectedTraders && filters.value.selectedTraders.length > 0)
      params.trader__user__username__in = filters.value.selectedTraders.join (",")

    // Support Filters
    if (filters.value.selectedTeams && filters.value.selectedTeams.length > 0)
      params.trader__team__name__in = filters.value.selectedTeams.join (",")

    // Head Support Filters (Only)
    if (filters.value.selectedMerchants && filters.value.selectedMerchants.length > 0)
      params.merchant__user__username__in = filters.value.selectedMerchants.join (",")

    // END Filters
  }

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
      filters.value.apply_filters = currentType.value !== 'all'
    }
    getOrders ()
  },
  { immediate: true },
)

onMounted (
  () => {
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
    <VRow v-if="authStore.is_authenticated()">
      <VCol cols="12">
        <VCard>
          <VCardTitle class="mt-2 ms-2">
            <VAvatar
              size="50"
              variant="text"
              color="primary"
              icon="tabler-arrow-down-left"
            />
            {{ t ('tabs.orders_in') }}
          </VCardTitle>
          <VCol cols="12">
            <VCard>
              <VCardText class="d-flex align-center flex-wrap gap-3">
                <VCardText
                  class="text-h5 mb-0"
                  style="padding: 0.5rem;"
                >
                  {{ t ('tabs.orders_in') }}
                </VCardText>

                <VSpacer />
                <VCol
                  cols="4"
                  sm="3"
                  md="2"
                  lg="1"
                >
                  <VSelect
                    v-model="filters.rowsPerPage"
                    :items="rowsPerPageOptions"
                    :label="$t('rows')"
                    item-title="name"
                    item-value="value"
                    scroll-strategy="close"
                    color="primary"
                  />
                </VCol>
                <VCol
                  cols="4"
                  sm="3"
                  md="2"
                  lg="1"
                >
                  <VSelect
                    v-model="filters.autoUpdateMode"
                    :items="autoUpdateModes"
                    :label="$t('auto_refresh')"
                    item-title="name"
                    item-value="value"
                    scroll-strategy="close"
                    color="primary"
                  />
                </VCol>
                <VProgressCircular
                  v-if="filters.autoUpdateMode"
                  v-model="autoUpdateProgress"
                  class="cursor-pointer"
                  :size="40"
                  :width="2"
                  color="primary"
                  @click="getOrders(true)"
                >
                  {{ autoUpdateProgressSeconds }}s
                </VProgressCircular>
                <VBtn
                  v-else
                  icon="tabler-refresh"
                  size="small"
                  @click="getOrders(true)"
                />
              </VCardText>

              <VExpansionPanels class="px-5 pb-5">
                <VExpansionPanel>
                  <VExpansionPanelTitle>
                    <div class="text-h6">
                      {{ $t ('filters') }}
                    </div>
                  </VExpansionPanelTitle>
                  <VExpansionPanelText>
                    <VCardText>
                      <VRow>
                        <!-- 👉 Select Role -->
                        <VCol
                          cols="12"
                          sm="5"
                        >
                          <AppSelect
                            v-model="filters.selectedStatus"
                            :label="$t('status')"
                            :items="filterOptions.status"
                            :item-title="option => $t (`order_status.${option.name.toLowerCase()}`)"
                            item-value="name"
                            multiple
                            clearable
                            clear-icon="tabler-x"
                            :prepend-inner-icon="filters.selectedStatus.length === filterOptions.status.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                            @click:prependInner="switchSelection(filterOptions.status, 'selectedStatus', 'name')"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                          sm="4"
                          md="3"
                          lg="2"
                        >
                          <AppSelect
                            v-model="filters.selectedPaymentSystems"
                            :label="$t('payment_systems')"
                            :items="filterOptions.payment_system"
                            item-title="name"
                            item-value="name"
                            multiple
                            clearable
                            clear-icon="tabler-x"
                            :prepend-inner-icon="filters.selectedPaymentSystems.length === filterOptions.payment_system.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                            @click:prependInner="switchSelection(filterOptions.payment_system, 'selectedPaymentSystems', 'name')"
                          />
                        </VCol>
                        <!-- 👉 Select Plan -->
                        <VCol
                          cols="12"
                          sm="6"
                        >
                          <AppDateTimePicker
                            v-model="filters.dateRange"
                            :label="$t('creation_date_range')"
                            :config="{ mode: 'range', enableTime: true, dateFormat: 'Y-m-d H:i'}"
                            clearable
                            clear-icon="tabler-x"
                          />
                        </VCol>
                        <!-- 👉 Select Status -->
                        <VCol
                          cols="12"
                          sm="3"
                        >
                          <AppTextField
                            v-model="filters.minAmount"
                            :label="$t('min_amount_fiat')"
                            type="number"
                            clearable
                            clear-icon="tabler-x"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                          sm="3"
                        >
                          <AppTextField
                            v-model="filters.maxAmount"
                            :label="$t('max_amount_fiat')"
                            type="number"
                            clearable
                            clear-icon="tabler-x"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                          sm="3"
                        >
                          <AppTextField
                            v-model="filters.minUSDAmount"
                            :label="$t('min_amount_usdt')"
                            type="number"
                            clearable
                            clear-icon="tabler-x"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                          sm="3"
                        >
                          <AppTextField
                            v-model="filters.maxUSDAmount"
                            :label="$t('max_amount_usdt')"
                            type="number"
                            clearable
                            clear-icon="tabler-x"
                          />
                        </VCol>
                        <VSpacer />
                        <VCol
                          cols="12"
                          sm="4"
                          md="4"
                        >
                          <AppSelect
                            v-model="filters.ordering"
                            :label="$t('ordering')"
                            :items="orderingTypes"
                            :item-title="option => $t (`orderings.${option.value.toLowerCase()}`)"
                            item-value="value"
                            clear-icon="tabler-x"
                          />
                        </VCol>
                      </VRow>
                    </VCardText>

                    <VDivider />
                    <VCardText class="d-flex flex-wrap py-4 gap-4">
                      <template
                        v-if="authStore.is_merchant()"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedCurrencies.length === filterOptions.currencies.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTraders.length === filterOptions.traders.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTeams.length === filterOptions.teams.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedCurrencies.length === filterOptions.currencies.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTrafficTypes.length === filterOptions.traffic_type.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTraders.length === filterOptions.traders.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTeams.length === filterOptions.teams.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedMerchants.length === filterOptions.merchants.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedCurrencies.length === filterOptions.currencies.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTrafficTypes.length === filterOptions.traffic_type.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTraders.length === filterOptions.traders.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTeams.length === filterOptions.teams.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTrafficTypes.length === filterOptions.traffic_type.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTraders.length === filterOptions.traders.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                              clear-icon="tabler-x"
                              :prepend-inner-icon="filters.selectedTrafficTypes.length === filterOptions.traffic_type.length ? 'tabler-square-check-filled': 'tabler-square-check'"
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
                    </VCardText>
                  </VExpansionPanelText>
                </VExpansionPanel>
              </VExpansionPanels>

              <VDivider />
              <VCardText class="d-flex flex-wrap py-4 gap-4">
                <VTooltip
                  location="right"
                >
                  <template #activator="{ props }">
                    <VChip
                      v-bind="props"
                      class="ms-1 px-3 font-weight-bold"
                      color="primary"
                      text-color="white"
                      size="lg"
                    >
                      $ {{ totalUSDAmount }}
                    </VChip>
                  </template>
                  <span>
                    {{ $t ('total_usd_amount') }}
                  </span>
                </VTooltip>
                <VTooltip
                  location="right"
                >
                  <template #activator="{ props }">
                    <VChip
                      v-bind="props"
                      class="ms-1 px-3 font-weight-bold"
                      color="primary"
                      text-color="white"
                      size="lg"
                    >
                      $ {{ totalComission }}
                    </VChip>
                  </template>
                  <span>
                    {{ $t ('total_commission') }}
                  </span>
                </VTooltip>
                <VTooltip
                  location="right"
                >
                  <template #activator="{ props }">
                    <VChip
                      v-bind="props"
                      class="ms-1 px-3 font-weight-bold"
                      color="info"
                      text-color="white"
                      size="lg"
                      prepend-icon="tabler-snowflake"
                    >
                      {{ holdAmount }}
                    </VChip>
                  </template>
                  <span>
                    {{ $t ('hold') }}
                  </span>
                </VTooltip>
                <VSpacer />
                <div class="app-user-search-filter d-flex align-center flex-wrap gap-4">
                  <!-- 👉 Search  -->
                  <div style="inline-size: 10rem;">
                    <VSwitch
                      v-model="filters.apply_filters"
                      :label="filters.apply_filters ? $t('apply_filters') : $t('not_apply_filters')"
                      @change="getOrders"
                    />
                  </div>
                  <div
                    v-if="authStore.is_merchant() && !authStore.is_team_lead() || authStore.is_support()"
                    style="inline-size: 12rem;"
                  >
                    <AppTextField
                      v-model="filters.searchMerchantOrderId"
                      :placeholder="$t ('merchant_order_id')"
                      density="compact"
                    />
                  </div>
                  <div style="inline-size: 10rem;">
                    <AppTextField
                      v-model="filters.searchQueryId"
                      placeholder="ID"
                      density="compact"
                    />
                  </div>
                  <div
                    v-if="!authStore.is_trader() && !authStore.is_team_lead()"
                    style="inline-size: 10rem;"
                  >
                    <AppTextField
                      v-model="filters.searchCustomerId"
                      :placeholder="$t ('customer_id')"
                      density="compact"
                    />
                  </div>
                  <div
                    v-if="!authStore.is_merchant()"
                    style="inline-size: 10rem;"
                  >
                    <AppTextField
                      v-model="filters.searchPaymentDetailsGroupId"
                      :placeholder="$t ('payment_details_group_id')"
                      density="compact"
                    />
                  </div>
                  <div
                    v-if="!authStore.is_merchant()"
                    style="inline-size: 10rem;"
                  >
                    <AppTextField
                      v-model="filters.searchPaymentDetailsGroupOwner"
                      :placeholder="$t ('payment_details_group_owner')"
                      density="compact"
                    />
                  </div>
                  <VBtn
                    :loading="exportLoading"
                    variant="tonal"
                    color="secondary"
                    prepend-icon="tabler-screen-share"
                    @click="exportOrders"
                  >
                    {{ $t ('export') }}
                  </VBtn>
                  <VBtn
                    color="primary"
                    prepend-icon="tabler-search"
                    @click="getOrders(true)"
                  >
                    {{ $t ('search') }}
                  </VBtn>
                </div>
              </VCardText>

              <VDivider />
              <!-- SECTION Table -->
              <VTable
                class="text-no-wrap invoice-list-table text-body-2"
              >
                <!-- 👉 Table head -->
                <thead>
                  <tr class="text-wrap">
                    <th scope="col">
                      {{ $t ('status').toUpperCase () }} / {{ $t ('completion_time').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('expires').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('amount').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('usd_amount').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('payment_system').toUpperCase () }}
                    </th>
                    <th
                      v-if="authStore.is_support() || authStore.is_trader()"
                      scope="col"
                    >
                      {{ $t ('payment_details').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('id').toUpperCase () }}
                    </th>
                    <!--                    <th -->
                    <!--                      v-if="authStore.is_support() || authStore.is_trader()" -->
                    <!--                      scope="col" -->
                    <!--                    > -->
                    <!--                      {{ $t ('traffic_type').toUpperCase () }} -->
                    <!--                    </th> -->
                    <th
                      v-if="authStore.is_support() || authStore.is_senior_trader()"
                      scope="col"
                    >
                      {{ $t ('trader').toUpperCase () }}
                    </th>
                    <th
                      v-if="authStore.is_head_of_support()"
                      scope="col"
                    >
                      {{ $t ('merchant').toUpperCase () }}
                    </th>
                    <th
                      v-if="(authStore.is_head_of_support() || authStore.is_merchant()) && !authStore.is_team_lead()"
                      scope="col"
                    >
                      {{ $t ('merchant_order_id').toUpperCase () }}
                    </th>
                    <!--                    <th -->
                    <!--                      scope="col" -->
                    <!--                    > -->
                    <!--                      {{ $t ('transaction_id').toUpperCase () }} -->
                    <!--                    </th> -->
                    <!--                    <th -->
                    <!--                      v-if="authStore.is_support()" -->
                    <!--                      scope="col" -->
                    <!--                    > -->
                    <!--                      {{ $t ('client_ip').toUpperCase () }} -->
                    <!--                    </th> -->
                    <th scope="col">
                      {{ $t ('date').toUpperCase () }}
                    </th>
                  </tr>
                </thead>

                <tbody>
                  <tr
                    v-for="(item, index) in items"
                    :key="item.id"
                    class="cursor-pointer"
                    :class="(item.id === orderItemId && isOrderInDrawerOpen) ? 'bg-light-primary' : index % 2 === 0 ? 'bg-light-secondary': ''"
                    @click="openOrderDetails (item)"
                  >
                    <td>
                      <VChip
                        size="small"
                        :color="resolveOrderInStatusVariantAndIcon(item.status).variant"
                        variant="tonal"
                        :prepend-icon="resolveOrderInStatusVariantAndIcon(item.status).icon"
                      >
                        {{ resolveOrderInStatusVariantAndIcon (item.status).text }}
                      </VChip>
                      <template
                        v-if="item.status === 'New'"
                      >
                        / {{ formatTimeDeltaSeconds (nowTime, parseInt (item.expires_at) * 1000) }}
                      </template>
                      <template
                        v-else
                      >
                        / {{
                          item.completion_date ? formatTimeDeltaSeconds (parseInt (item.creation_date) * 1000, parseInt (item.completion_date) * 1000) : $t('not_completed')
                        }}
                      </template>
                      <VTooltip
                        v-if="!authStore.is_merchant() && item.auto_closed"
                        location="right"
                      >
                        <template #activator="{ props }">
                          <VIcon
                            v-bind="props"
                            color="error"
                            icon="tabler-robot-face"
                          />
                        </template>
                        <span>
                          {{ $t ('auto_closed') }}
                        </span>
                      </VTooltip>
                    </td>
                    <td v-if="['Money sent by user'].includes(item.status)">
                      <VChip
                        size="small"
                        :color="formatDeltaTimeVariantAndIcon(parseInt(item.expires_at) * 1000 - nowTime).variant"
                        variant="tonal"
                        :prepend-icon="formatDeltaTimeVariantAndIcon(parseInt(item.expires_at) * 1000 - nowTime).icon"
                      >
                        {{ formatDeltaTimeVariantAndIcon (parseInt (item.expires_at) * 1000 - nowTime).text }}
                      </VChip>
                    </td>
                    <td v-else>
                      {{ $t ('no_data') }}
                    </td>
                    <td>
                      {{ item.currency }}&nbsp;{{ item.amount }}
                    </td>
                    <td>
                      USD&nbsp;{{ item.usd_amount }}
                    </td>
                    <td>
                      {{ item.payment_system }}
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
                      <VTooltip
                        location="top"
                      >
                        <template #activator="{ props }">
                          <VBtn
                            size="small"
                            variant="text"
                            class="text-lowercase"
                            v-bind="props"
                            @click.stop="copyToClipboard (item.id, 'Order ID copied!', 'success')"
                          >
                            {{ formatUUID (item.id) }}
                          </VBtn>
                        </template>
                        <span>
                          {{ item.id }}
                        </span>
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
                      <VTooltip
                        location="top"
                      >
                        <template #activator="{ props }">
                          <VBtn
                            size="small"
                            variant="text"
                            class="text-lowercase"
                            v-bind="props"
                            @click.stop="copyToClipboard (item.merchant_order_id, 'Merchant Order ID copied!', 'success')"
                          >
                            {{ item.merchant_order_id }}
                          </VBtn>
                        </template>
                        <span>
                          {{ item.merchant_order_id }}
                        </span>
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
                    <td class="font-weight-bold">
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
                      class="text-center text-body-1 justify-center align-center"
                    >
                      {{ loadMessage.message }}
                      <VProgressCircular
                        v-if="loadMessage.status === 0"
                        :width="3"
                        color="primary"
                        indeterminate
                      />
                      <VIcon
                        v-else-if="loadMessage.status === 1"
                        color="success"
                        icon="tabler-tick"
                      />
                      <VIcon
                        v-else
                        color="error"
                        icon="tabler-x"
                      />
                    </td>

                    <td
                      colspan="12"
                      class="text-center text-body-1 justify-center align-center"
                    />
                  </tr>
                </tfoot>
              </VTable>
              <!-- !SECTION -->

              <VDivider />

              <!-- SECTION Pagination -->
              <VCardText class="d-flex align-center flex-wrap justify-space-between gap-4 py-4">
                <!-- 👉  Pagination meta -->
                <span class="text-sm text-disabled">{{ paginationData }}</span>

                <!-- 👉 Pagination -->
                <VPagination
                  v-model="currentPage"
                  size="small"
                  :total-visible="5"
                  :length="totalPage"
                  @next="selectedRows = []"
                  @prev="selectedRows = []"
                />
              </VCardText>
              <!-- !SECTION -->
            </VCard>
          </VCol>
        </VCard>
        <OrderInDrawer
          v-model:isDrawerOpen="isOrderInDrawerOpen"
          v-model:order-id="orderItemId"
          v-model:time="nowTime"
        />
      </VCol>
    </VRow>
  </div>
</template>
