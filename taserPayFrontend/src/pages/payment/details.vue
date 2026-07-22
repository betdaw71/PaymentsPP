<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { useTradeStore } from "@/stores/useTradeStore"
import {
  capitalize,
  formatUUID,
  resolvePaymentDetailsStatusVariantAndIcon,
  formatTimeDelta, formatTimeDeltaSeconds,
} from "@core/utils/formatters"
import { useBaseStore } from "@/stores/useBaseStore"
import ViewPaymentDetailsDrawer from "@/views/user/ViewPaymentDetailsDrawer.vue"
import AddPaymentDetailsDrawer from "@/views/user/AddPaymentDetailsDrawer.vue"

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
const nowTime = ref (Date.now ())
const isViewDrawerOpen = ref (false)
const isAddDrawerOpen = ref (false)

setInterval (() => {
  nowTime.value = Date.now ()
}, 1000)


const filters = ref (
  structuredClone (toRaw (baseStore.payment_details_filters)),
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
    value: "-total_volume",
    name: "Total Volume (Desc)",
  },
  {
    value: "total_volume",
    name: "Total Volume (Asc)",
  },
  {
    value: "-amount",
    name: "Amount (Desc)",
  },
  {
    value: "amount",
    name: "Amount (Asc)",
  },
]


const rowsPerPageOptions = [
  { value: 10, name: "x10" },
  { value: 20, name: "x20" },
  { value: 50, name: "x50" },
]

const getFilters = async () => {
  baseStore.getFiltersPaymentDetails ({}).then (
    response => {
      if (response.error)
        throw response.error
      filterOptions.value = response.data

      // if (filters.value.selectedStatus && filters.value.selectedStatus.length > 0)
      // filters.value.selectedStatus = response.data.status.filter (item => filters.value.selectedStatus.includes (item.value))
      if (filters.value.selectedPaymentSystems && filters.value.selectedPaymentSystems.length > 0)
        filters.value.selectedPaymentSystems = response.data.payment_system.filter (item => filters.value.selectedPaymentSystems.includes (item.value))
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

const getPaymentDetails = async () => {
  loadMessage.value = {
    message: t ('data.loading'),
    status: 0,
  }
  items.value = []

  const params = {
    per_page: filters.value.rowsPerPage,
    page: currentPage.value,
  }


  // Base Filters
  if (filters.value.ordering)
    params.ordering = filters.value.ordering
  if (filters.value.apply_filters) {
    if (filters.value.searchQueryId)
      params.id = filters.value.searchQueryId
    if (filters.value.selectedStatus && filters.value.selectedStatus.length > 0)
      params.status__in = filters.value.selectedStatus.join (",")
    if (filters.value.selectedPaymentSystems && filters.value.selectedPaymentSystems.length > 0)
      params.payment_system__name__in = filters.value.selectedPaymentSystems.join (",")

    if (filters.value.selectedCurrencies && filters.value.selectedCurrencies.length > 0)
      params.currency__symbol__in = filters.value.selectedCurrencies.join (",")

    // Trader Filters

    if (filters.value.selectedTrafficTypes && filters.value.selectedTrafficTypes.length > 0)
      params.excluded_traffic__name__in = filters.value.selectedTrafficTypes.join (",")

    // Trader Boss Filters (Only)
    if (filters.value.selectedTraders && filters.value.selectedTraders.length > 0)
      params.trader__user__username__in = filters.value.selectedTraders.join (",")

    // Support Filters
    if (filters.value.selectedTeams && filters.value.selectedTeams.length > 0)
      params.trader__team__name__in = filters.value.selectedTeams.join (",")

    if (filters.value.searchOwner)
      params.owner = filters.value.searchOwner
  }

  // END Filters


  baseStore.getPaymentDetails (params).then (response => {
    if (response.error) {
      throw response.error
    }
    console.log ({ response })
    items.value = response.data.results
    total.value = response.data.count
    totalPage.value = parseInt (total.value / filters.value.rowsPerPage) + (total.value % filters.value.rowsPerPage === 0 ? 0 : 1) || 1
    if (items.value.length === 0) {
      loadMessage.value = {
        message: t ('data.empty'),
        status: 2,
      }
    }
  }).catch (error => {
    loadMessage.value = {
      message: t ('data.error'),
      status: 2,
    }
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
  })
}

onMounted (
  async () => {
    await getFilters ()
    getPaymentDetails ()
  },
)


watch (
  () => {
    return {
      currentPage: currentPage.value,
      rowsPerPage: filters.value.rowsPerPage,
    }
  },
  () => {
    getPaymentDetails ()
  },
  { deep: true },
)

const createPaymentDetails = () => {
  isAddDrawerOpen.value = true
}

watchEffect (() => {
  if (currentPage.value > totalPage.value)
    currentPage.value = totalPage.value
})


const paginationData = computed (() => {
  const firstIndex = items.value.length ? (currentPage.value - 1) * filters.value.rowsPerPage + 1 : 0
  const lastIndex = items.value.length + (currentPage.value - 1) * filters.value.rowsPerPage

  return `${t ('pagination.showing')} ${firstIndex} ${t ('pagination.to')} ${lastIndex} ${t ('pagination.of')} ${total.value} ${t ('pagination.entries')}`
})

watch (
  () => filters.value,
  () => {
    baseStore.payment_details_filters = structuredClone (toRaw (filters.value))
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

const itemId = ref (null)

const openItemDetails = item => {
  itemId.value = item.id
  isViewDrawerOpen.value = true
}

const changeStatus = (item, status) => {
  // 0 - in_active
  // 1 - out_active
  // 2 - both
  const data = { status: 2 }
  if (item.in_active) { // prev - 0
    if (item.out_active) { // prev - 2
      if (status === "in") { // out - true, in - false
        data.status = 1
      } else { // out - false, in - true
        data.status = 0
      }
    } else { // prev - 0
      if (status === "in") { // out - false, in - false
        data.status = 1
      } else { // out - true, in - true
        data.status = 2
      }
    }
  } else { // prev - 1
    if (item.out_active) { // prev - 2
      if (status === "in") { // out - true, in - true
        data.status = 2
      } else { // out - false, in - true
        data.status = 0
      }
    } else { // prev - -1
      if (status === "in") { // out - false, in - true
        data.status = 0
      } else { // out - true, in - false
        data.status = 1
      }
    }
  }
  baseStore.changePaymentDetailsDirectionStatusById(data, item.id).then (response => {
    if (response.error) {
      throw response.error
    }
    if (data.status === 2) {
      items.value.forEach (currentItem => {
        if (item.id === currentItem.id) {
          currentItem.in_active = true
          currentItem.out_active = true
        }
      })
    } else if (data.status === 1) {
      items.value.forEach (currentItem => {
        if (item.id === currentItem.id) {
          currentItem.in_active = false
          currentItem.out_active = true
        }
      })
    } else {
      items.value.forEach (currentItem => {
        if (item.id === currentItem.id) {
          currentItem.in_active = true
          currentItem.out_active = false
        }
      })
    }
    snackbar.value = {
      enabled: true,
      type: "success",
      message: t ('success') + "!",
    }
  }).catch (error => {
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
  })
}

const filterPanelExpanded = ref(true)

const activeFilterCount = computed(() => {
  const f = filters.value
  let n = 0
  if (f.searchQueryId) n++
  if (f.searchOwner) n++
  if (f.selectedStatus?.length) n++
  if (f.selectedPaymentSystems?.length) n++
  if (f.selectedCurrencies?.length) n++
  if (f.selectedTrafficTypes?.length) n++
  if (f.selectedTraders?.length) n++
  if (f.selectedTeams?.length) n++
  if (f.ordering && f.ordering !== '-total_volume') n++
  return n
})

const resetFilters = () => {
  const { rowsPerPage, apply_filters } = filters.value
  filters.value = {
    searchOwner: '',
    rowsPerPage,
    selectedStatus: [],
    selectedPaymentSystems: [],
    selectedCurrencies: [],
    selectedTrafficTypes: [],
    selectedTraders: [],
    selectedTeams: [],
    searchQueryId: '',
    ordering: '-total_volume',
    apply_filters,
  }
  getPaymentDetails()
}
</script>


<template>
  <VCol>
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
              icon="tabler-credit-card"
            />
            {{ t ('tabs.payment_details') }}
          </VCardTitle>
          <VCol cols="12">
            <VCard>
              <VCardText class="d-flex align-center flex-wrap gap-3">
                <VCardText
                  class="text-h5 mb-0"
                  style="padding: 0.5rem;"
                >
                  {{ t ('tabs.payment_details') }}
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
                <UiButton
                  variant="ghost"
                  size="small"
                  icon
                  @click="getPaymentDetails"
                >
                  <VIcon
                    icon="tabler-refresh"
                    size="18"
                  />
                </UiButton>
              </VCardText>

              <UiFilterPanel
                v-model:expanded="filterPanelExpanded"
                :active-count="activeFilterCount"
                :title="$t('filters')"
                class="mx-5 mb-2"
                @apply="getPaymentDetails"
                @reset="resetFilters"
              >
                    <VCardText class="pa-0">
                      <VRow>
                        <!-- 👉 Select Role -->
                        <VCol
                          cols="12"
                          sm="4"
                          md="3"
                          lg="2"
                        >
                          <AppSelect
                            v-model="filters.selectedStatus"
                            :label="$t('status')"
                            :items="filterOptions.status"
                            :item-title="option => $t (`details_status.${option.name.toLowerCase()}`)"
                            item-value="value"
                            multiple
                            clearable
                            clear-icon="tabler-x"
                            :prepend-inner-icon="filters.selectedStatus.length === filterOptions.status.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                            @click:prepend-inner="switchSelection(filterOptions.status, 'selectedStatus', 'value')"
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
                            @click:prepend-inner="switchSelection(filterOptions.payment_system, 'selectedPaymentSystems', 'name')"
                          />
                        </VCol>
                        <!-- 👉 Select Status -->
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
                          md="4"
                        >
                          <AppSelect
                            v-model="filters.ordering"
                            :label="$t ('ordering')"
                            :items="orderingTypes"
                            :item-title="option => $t (`orderings.${option.value.toLowerCase()}`)"
                            item-value="value"
                            clear-icon="tabler-x"
                          />
                        </VCol>
                      </VRow>
                    </VCardText>
                    <template
                      v-if="authStore.is_support() || authStore.is_senior_trader()"
                    >
                      <VDivider />
                      <VCardText class="d-flex flex-wrap py-4 gap-4">
                        <VRow>
                          <VCol
                            v-if="authStore.is_support()"
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
                            v-if="authStore.is_support()"
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
                      </VCardText>
                    </template>
              </UiFilterPanel>

              <VDivider />
              <VCardText class="d-flex flex-wrap py-4 gap-4">
                <UiButton
                  v-if="authStore.is_trader()"
                  variant="primary"
                  size="small"
                  @click="createPaymentDetails"
                >
                  <VIcon
                    icon="tabler-plus"
                    size="16"
                    start
                  />
                  {{ $t('create') }}
                </UiButton>
                <VSpacer />
                <UiFilterBar
                  class="flex-grow-1"
                  :active-count="activeFilterCount"
                  @apply="getPaymentDetails"
                  @reset="resetFilters"
                >
                  <div style="inline-size: 10rem;">
                    <VSwitch
                      v-model="filters.apply_filters"
                      :label="filters.apply_filters ? $t('apply_filters') : $t('not_apply_filters')"
                      color="primary"
                      hide-details
                      density="compact"
                      @change="getPaymentDetails"
                    />
                  </div>
                  <div style="inline-size: 10rem;">
                    <AppTextField
                      v-model="filters.searchQueryId"
                      placeholder="ID"
                      density="compact"
                      class="ui-field--mono"
                    />
                  </div>
                  <div style="inline-size: 10rem;">
                    <AppTextField
                      v-model="filters.searchOwner"
                      placeholder="Owner"
                      density="compact"
                    />
                  </div>
                </UiFilterBar>
              </VCardText>

              <VDivider />
              <!-- SECTION Table -->
              <VTable
                class="text-no-wrap invoice-list-table text-body-2"
              >
                <!-- 👉 Table head -->
                <thead>
                  <tr class="text-wrap">
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('status').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('directions').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('owner').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('payment_system').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('balance').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('volume').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('total_volume').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('id').toUpperCase () }}
                    </th>
                    <th
                      v-if="authStore.is_senior_trader() || authStore.is_support()"
                      scope="col"
                    >
                      {{ $t ('trader').toUpperCase () }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(item, index) in items"
                    :key="item.id"
                    class="cursor-pointer"
                    :class="(item.id === itemId && isViewDrawerOpen) ? 'bg-light-primary' : index % 2 === 0 ? 'bg-light-secondary': ''"
                    @click="openItemDetails (item)"
                  >
                    <td>
                      <VChip
                        size="small"
                        :color="resolvePaymentDetailsStatusVariantAndIcon(item.status).variant"
                        variant="tonal"
                        :prepend-icon="resolvePaymentDetailsStatusVariantAndIcon(item.status).icon"
                      >
                        {{ resolvePaymentDetailsStatusVariantAndIcon (item.status).text }}
                      </VChip>
                    </td>
                    <td>
                      <VTooltip
                        location="top"
                      >
                        <template #activator="{ props }">
                          <VBtn
                            v-bind="props"
                            size="xs"
                            class="ms-2"
                            :color="item.out_active ? 'success': 'error'"
                            icon="tabler-circle-arrow-up-right"
                            :disabled="!authStore.is_trader()"
                            @click.stop="changeStatus(item, 'out')"
                          />
                        </template>
                        <span>
                          {{ item.out_active ? $t ('out_active') : $t ('out_not_active') }}
                        </span>
                      </VTooltip>
                      <VTooltip
                        location="top"
                      >
                        <template #activator="{ props }">
                          <VBtn
                            v-bind="props"
                            size="xs"
                            class="ms-2"
                            :color="item.in_active ? 'success': 'error'"
                            icon="tabler-circle-arrow-down-left"
                            :disabled="!authStore.is_trader()"
                            @click.stop="changeStatus(item, 'in')"
                          />
                        </template>
                        <span>
                          {{ item.in_active ? $t ('in_active') : $t ('in_not_active') }}
                        </span>
                      </VTooltip>
                    </td>
                    <td>
                      {{ item.owner }}
                    </td>
                    <td>
                      {{ item.payment_system }}
                    </td>
                    <td>
                      {{ item.amount }}&nbsp;{{ item.currency }}
                    </td>
                    <td>
                      {{ item.current_volume }} / {{ item.limit_per_period }}
                    </td>
                    <td>
                      {{ item.total_volume }}
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
                            @click.stop="copyToClipboard (item.id, 'Details ID copied!', 'success')"
                          >
                            {{ formatUUID (item.id) }}
                          </VBtn>
                        </template>
                        <span>
                          {{ item.id }}
                        </span>
                      </VTooltip>
                    </td>
                    <td
                      v-if="authStore.is_senior_trader() || authStore.is_support()"
                    >
                      <VChip
                        color="alternative"
                        text-color="white"
                        small
                      >
                        @{{ item.trader }}
                      </VChip>
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
        <ViewPaymentDetailsDrawer
          v-model:isDrawerOpen="isViewDrawerOpen"
          v-model:itemId="itemId"
          v-model:time="nowTime"
        />
        <AddPaymentDetailsDrawer
          v-if="authStore.is_trader()"
          v-model:isDrawerOpen="isAddDrawerOpen"
          v-model:time="nowTime"
          @update:items="getPaymentDetails"
        />
      </VCol>
    </VRow>
  </vcol>
</template>

<!-- <style> -->
<!-- /*.v-table&#45;&#45;density-default > .v-table__wrapper > table > tbody > tr > th, .v-table&#45;&#45;density-default > .v-table__wrapper > table > thead > tr > th, .v-table&#45;&#45;density-default > .v-table__wrapper > table > tfoot > tr > th,td{*/ -->

<!-- /*  width: 50px !important;*/ -->
<!-- //} -->
<!-- </style> -->
