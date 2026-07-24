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
  // Filters always apply (Variant A — no apply_filters toggle)
  if (filters.value.searchQueryId)
    params.id = filters.value.searchQueryId
  if (filters.value.selectedStatus && filters.value.selectedStatus.length > 0)
    params.status__in = filters.value.selectedStatus.join (",")
  if (filters.value.selectedPaymentSystems && filters.value.selectedPaymentSystems.length > 0)
    params.payment_system__name__in = filters.value.selectedPaymentSystems.join (",")
  if (filters.value.selectedCurrencies && filters.value.selectedCurrencies.length > 0)
    params.currency__symbol__in = filters.value.selectedCurrencies.join (",")
  if (filters.value.selectedTrafficTypes && filters.value.selectedTrafficTypes.length > 0)
    params.excluded_traffic__name__in = filters.value.selectedTrafficTypes.join (",")
  if (filters.value.selectedTraders && filters.value.selectedTraders.length > 0)
    params.trader__user__username__in = filters.value.selectedTraders.join (",")
  if (filters.value.selectedTeams && filters.value.selectedTeams.length > 0)
    params.trader__team__name__in = filters.value.selectedTeams.join (",")
  if (filters.value.searchOwner)
    params.owner = filters.value.searchOwner


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

const filterPanelExpanded = ref(false)

const countAdvancedFilters = f => {
  let n = 0
  if (f.selectedStatus?.length) n++
  if (f.selectedPaymentSystems?.length) n++
  if (f.selectedCurrencies?.length) n++
  if (f.selectedTrafficTypes?.length) n++
  if (f.selectedTraders?.length) n++
  if (f.selectedTeams?.length) n++
  if (f.ordering && f.ordering !== '-total_volume') n++
  return n
}

const advancedFilterCount = computed(() => countAdvancedFilters(filters.value))

const activeFilterChips = computed(() => {
  const chips = []
  const f = filters.value

  if (f.searchQueryId)
    chips.push({ key: 'searchQueryId', label: `ID: ${f.searchQueryId}` })
  if (f.searchOwner)
    chips.push({ key: 'searchOwner', label: `${t('owner')}: ${f.searchOwner}` })

  f.selectedStatus?.forEach(status => {
    chips.push({
      key: `status:${status}`,
      label: `${t('status')}: ${t(`details_status.${status.toLowerCase()}`)}`,
    })
  })
  f.selectedPaymentSystems?.forEach(ps => {
    chips.push({ key: `ps:${ps}`, label: `${t('payment_systems')}: ${ps}` })
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

  if (f.ordering && f.ordering !== '-total_volume') {
    const orderingLabel = orderingTypes.find(o => o.value === f.ordering)?.name ?? f.ordering
    chips.push({ key: 'ordering', label: `${t('ordering')}: ${orderingLabel}` })
  }

  return chips
})

const removeFilterChip = key => {
  const f = filters.value
  const scalarKeys = {
    searchQueryId: '',
    searchOwner: '',
    ordering: '-total_volume',
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
  }

  searchPaymentDetails()
}

const toggleFilterPanel = () => {
  filterPanelExpanded.value = !filterPanelExpanded.value
}

const searchPaymentDetails = () => {
  currentPage.value = 1
  getPaymentDetails()
}

const resetFilters = () => {
  const { rowsPerPage } = filters.value
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
  }
  searchPaymentDetails()
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
            icon="lucide:credit-card"
          />
          <h1 class="ui-workspace__title">
            {{ t('tabs.payment_details') }}
          </h1>
        </div>
      </template>
      <template #actions>
        <UiButton
          v-if="authStore.is_trader()"
          variant="primary"
          size="small"
          @click="createPaymentDetails"
        >
          <VIcon
            icon="lucide:plus"
            size="16"
            start
          />
          {{ $t('create') }}
        </UiButton>
        <UiButton
          variant="ghost"
          size="small"
          icon
          @click="getPaymentDetails"
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
            <AppTextField
              v-model="filters.searchQueryId"
              :label="$t('id')"
              density="compact"
              class="ui-field--mono"
              @keydown.enter="searchPaymentDetails"
            />
          </div>
          <div class="ui-orders-search__field">
            <AppTextField
              v-model="filters.searchOwner"
              :label="$t('owner')"
              density="compact"
              @keydown.enter="searchPaymentDetails"
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
            @click="searchPaymentDetails"
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
          @apply="searchPaymentDetails"
          @reset="resetFilters"
        >
          <UiFilterSection :title="$t('filter_section_status')">
            <VRow dense>
              <VCol
                cols="12"
                sm="6"
                md="4"
              >
                <AppSelect
                  v-model="filters.selectedStatus"
                  :label="$t('status')"
                  :items="filterOptions.status"
                  :item-title="option => $t(`details_status.${option.name.toLowerCase()}`)"
                  item-value="value"
                  multiple
                  clearable
                  clear-icon="lucide:x"
                  :prepend-inner-icon="filters.selectedStatus.length === filterOptions.status.length ? 'lucide:square-check': 'lucide:square'"
                  @click:prepend-inner="switchSelection(filterOptions.status, 'selectedStatus', 'value')"
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
                  @click:prepend-inner="switchSelection(filterOptions.payment_system, 'selectedPaymentSystems', 'name')"
                />
              </VCol>
              <VCol
                cols="12"
                sm="6"
                md="4"
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
                sm="6"
                md="4"
              >
                <AppSelect
                  v-model="filters.ordering"
                  :label="$t('ordering')"
                  :items="orderingTypes"
                  :item-title="option => $t(`orderings.${option.value.toLowerCase()}`)"
                  item-value="value"
                  clear-icon="lucide:x"
                />
              </VCol>
            </VRow>
          </UiFilterSection>

          <UiFilterSection
            v-if="authStore.is_support() || authStore.is_senior_trader()"
            :title="$t('filter_section_people')"
          >
            <VRow dense>
              <VCol
                v-if="authStore.is_support()"
                cols="12"
                sm="6"
                md="4"
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
                sm="6"
                md="4"
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
                v-if="authStore.is_support()"
                cols="12"
                sm="6"
                md="4"
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
          </UiFilterSection>
        </UiFilterPanel>
      </div>

      <UiDataTable :loading="loadMessage.status === 0">
                <thead>
                  <tr>
                    <th scope="col">
                      {{ $t('status') }}
                    </th>
                    <th scope="col">
                      {{ $t('directions') }}
                    </th>
                    <th scope="col">
                      {{ $t('owner') }}
                    </th>
                    <th scope="col">
                      {{ $t('payment_system') }}
                    </th>
                    <th scope="col" class="text-end">
                      {{ $t('balance') }}
                    </th>
                    <th scope="col" class="text-end">
                      {{ $t('volume') }}
                    </th>
                    <th scope="col" class="text-end">
                      {{ $t('total_volume') }}
                    </th>
                    <th scope="col">
                      {{ $t('id') }}
                    </th>
                    <th
                      v-if="authStore.is_senior_trader() || authStore.is_support()"
                      scope="col"
                    >
                      {{ $t('trader') }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(item, index) in items"
                    :key="item.id"
                    class="cursor-pointer"
                    :class="{
                      'ui-table-row--selected': item.id === itemId && isViewDrawerOpen,
                      'ui-table-row--alt': index % 2 === 0,
                    }"
                    @click="openItemDetails (item)"
                  >
                    <td class="ui-data-table__cell--status">
                      <VChip
                            size="small"
                            :color="resolvePaymentDetailsStatusVariantAndIcon(item.status).variant"
                            variant="tonal"
                            :prepend-icon="resolvePaymentDetailsStatusVariantAndIcon(item.status).icon"
                          >
                            {{ resolvePaymentDetailsStatusVariantAndIcon(item.status).text }}
                          </VChip>
                    </td>
                    <td>
                      <div class="d-flex align-center gap-1">
                        <VTooltip location="top">
                          <template #activator="{ props }">
                            <VBtn
                              v-bind="props"
                              size="x-small"
                              :color="item.out_active ? 'success': 'error'"
                              icon="lucide:arrow-up-right"
                              variant="flat"
                              :disabled="!authStore.is_trader()"
                              @click.stop="changeStatus(item, 'out')"
                            />
                          </template>
                          <span>{{ item.out_active ? $t ('out_active') : $t ('out_not_active') }}</span>
                        </VTooltip>
                        <VTooltip location="top">
                          <template #activator="{ props }">
                            <VBtn
                              v-bind="props"
                              size="x-small"
                              :color="item.in_active ? 'success': 'error'"
                              icon="lucide:arrow-down-left"
                              variant="flat"
                              :disabled="!authStore.is_trader()"
                              @click.stop="changeStatus(item, 'in')"
                            />
                          </template>
                          <span>{{ item.in_active ? $t ('in_active') : $t ('in_not_active') }}</span>
                        </VTooltip>
                      </div>
                    </td>
                    <td class="ui-cell-primary">
                      {{ item.owner }}
                    </td>
                    <td class="ui-cell-primary">
                      {{ item.payment_system }}
                    </td>
                    <td class="ui-data-table__cell--num">
                      <span class="ui-cell-amount">{{ item.amount }}</span>
                      <span class="ui-cell-currency">{{ item.currency }}</span>
                    </td>
                    <td class="ui-data-table__cell--num ui-cell-meta">
                      {{ item.current_volume }} / {{ item.limit_per_period }}
                    </td>
                    <td class="ui-data-table__cell--num">
                      <span class="ui-cell-amount">{{ item.total_volume }}</span>
                    </td>
                    <td>
                      <VTooltip location="top">
                        <template #activator="{ props }">
                          <button
                            type="button"
                            class="ui-copy-id"
                            v-bind="props"
                            @click.stop="copyToClipboard (item.id, 'Details ID copied!', 'success')"
                          >
                            {{ formatUUID (item.id) }}
                          </button>
                        </template>
                        <span>{{ item.id }}</span>
                      </VTooltip>
                    </td>
                    <td
                      v-if="authStore.is_senior_trader() || authStore.is_support()"
                    >
                      <VChip
                        color="alternative"
                        text-color="white"
                        size="small"
                      >
                        @{{ item.trader }}
                      </VChip>
                    </td>
                  </tr>
                </tbody>

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
  </div>
</template>
