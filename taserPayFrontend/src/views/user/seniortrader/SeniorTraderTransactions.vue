<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { useTradeStore } from "@/stores/useTradeStore"
import { formatUUID, resolveTransactionTypeVariantAndIcon } from "@core/utils/formatters"
import FilterTransactions from "@/views/user/FilterTransactions.vue"
import { useBaseStore } from "@/stores/useBaseStore"

const { t } = useI18n ()
const tradeStore = useTradeStore ()
const authStore = useAuthStore ()
const baseStore = useBaseStore ()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})


const currentPage = ref (1)
const totalPage = ref (1)
const total = ref (0)
const items = ref ([])
const selectedRows = ref ([])
const isUserFilterFromTransactionsDialogOpen = ref (false)
const isUserFilterToTransactionsDialogOpen = ref (false)

const filters = ref (
  structuredClone (toRaw (baseStore.transactions_filters)),
)

const rowsPerPageOptions = [
  { value: 10, name: "x10" },
  { value: 20, name: "x20" },
  { value: 50, name: "x50" },
]

const baseTransactionsFilter = {
  'balance__available__user__username__in': [],
  'balance_available_merchant_user__username__in': [],
  'balance__available__team__name__in': [],
  'balance__type__in': [],
}

// const transactionsFilterFrom = ref (structuredClone (toRaw (baseTransactionsFilter)))
//
// const transactionsFilterTo = ref (structuredClone (toRaw (baseTransactionsFilter)))

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

const itemTypes = [
  { value: "Freeze", name: "Freeze" },
  { value: "Charge", name: "Charge" },
  { value: "Deposit", name: "Deposit" },
  { value: "Transfer", name: "Transfer" },
  { value: "Withdrawal", name: "Withdrawal" },
]

const orderingTypes = [
  {
    value: "-creation_date",
    name: "Creation Date (Desc)",
  },
  {
    value: "creation_date",
    name: "Creation Date (Asc)",
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
    value: "-transaction_type",
    name: "Type (Desc)",
  },
  {
    value: "transaction_type",
    name: "Type (Asc)",
  },
]

const getTransactions = async () => {
  loadMessage.value = {
    message: t ('data.loading'),
    status: 0,
  }
  items.value = []

  const params = {
    per_page: filters.value.rowsPerPage,
    page: currentPage.value,
  }

  if (filters.value.ordering)
    params.ordering = filters.value.ordering
  if (filters.value.from.balance__available__team__name__in && filters.value.from.balance__available__team__name__in.length > 0)
    params.from_balance__available__team__name__in = filters.value.from.balance__available__team__name__in.join (",")
  if (filters.value.from.balance__available__user__username__in && filters.value.from.balance__available__user__username__in.length > 0)
    params.from_balance__available__user__username__in = filters.value.from.balance__available__user__username__in.join (",")
  if (filters.value.from.balance__available_merchant__user__username__in && filters.value.from.balance__available_merchant__user__username__in.length > 0)
    params.from_balance__available_merchant__user__username__in = filters.value.from.balance__available_merchant__user__username__in.join (",")
  if (filters.value.from.balance__type__in && filters.value.from.balance__type__in.length > 0)
    params.from_balance__type__in = filters.value.from.balance__type__in.join (",")
  if (filters.value.to.balance__available__team__name__in && filters.value.to.balance__available__team__name__in.length > 0)
    params.to_balance__available__team__name__in = filters.value.to.balance__available__team__name__in.join (",")
  if (filters.value.to.balance__available__user__username__in && filters.value.to.balance__available__user__username__in.length > 0)
    params.to_balance__available__user__username__in = filters.value.to.balance__available__user__username__in.join (",")
  if (filters.value.to.balance__available_merchant__user__username__in && filters.value.to.balance__available_merchant__user__username__in.length > 0)
    params.to_balance__available_merchant__user__username__in = filters.value.to.balance__available_merchant__user__username__in.join (",")
  if (filters.value.to.balance__type__in && filters.value.to.balance__type__in.length > 0)
    params.to_balance__type__in = filters.value.to.balance__type__in.join (",")
  if (filters.value.searchQueryId)
    params.id = filters.value.searchQueryId
  if (filters.value.selectedType && filters.value.selectedType.length > 0)
    params.transaction_type__name__in = filters.value.selectedType.join (",")
  if (filters.value.minAmount)
    params.value__gte = filters.value.minAmount
  if (filters.value.maxAmount)
    params.value__lte = filters.value.maxAmount
  if (filters.value.searchQueryIn)
    params.linked_in_order = filters.value.searchQueryIn
  if (filters.value.searchQueryOut)
    params.linked_out_order = filters.value.searchQueryOut
  if (filters.value.dateRange && filters.value.dateRange.includes (" to "))
    params.creation_date__range = filters.value.dateRange.replace (" to ", ",")
  tradeStore.getTradeTransaction (params).then (response => {
    if (response.error) {
      throw response.error
    }
    items.value = response.data.results
    console.log ({ items: items.value })
    total.value = response.data.count
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


watch (
  () => {
    return {
      currentPage: currentPage.value,
      rowsPerPage: filters.value.rowsPerPage,
    }
  },
  () => {
    getTransactions ()
  },
  { deep: true },
)
onMounted(
  () => {
    getTransactions ()
  },
)


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
    baseStore.transactions_filters = structuredClone (toRaw (filters.value))
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
const filterPanelExpanded = ref(false)

const countPersonFilterFields = filterObj => {
  let n = 0
  if (filterObj.balance__available__user__username__in?.length) n++
  if (filterObj.balance__available_merchant__user__username__in?.length) n++
  if (filterObj.balance__available__team__name__in?.length) n++
  if (filterObj.balance__type__in?.length) n++
  return n
}

const countAdvancedFilters = f => {
  let n = 0
  if (f.selectedType?.length) n++
  if (f.minAmount) n++
  if (f.maxAmount) n++
  if (f.dateRange) n++
  if (f.ordering && f.ordering !== '-creation_date') n++
  n += countPersonFilterFields(f.from)
  n += countPersonFilterFields(f.to)
  return n
}

const advancedFilterCount = computed(() => countAdvancedFilters(filters.value))

const addPersonFilterChips = (chips, side, filterObj) => {
  const sideLabel = side === 'from' ? t('from_filters') : t('to_filters')
  filterObj.balance__available__user__username__in?.forEach(v => {
    chips.push({ key: `${side}:user:${v}`, label: `${sideLabel} ${t('filter_transactions.traders')}: ${v}` })
  })
  filterObj.balance__available_merchant__user__username__in?.forEach(v => {
    chips.push({ key: `${side}:merchant:${v}`, label: `${sideLabel} ${t('filter_transactions.merchants')}: ${v}` })
  })
  filterObj.balance__available__team__name__in?.forEach(v => {
    chips.push({ key: `${side}:team:${v}`, label: `${sideLabel} ${t('filter_transactions.teams')}: ${v}` })
  })
  filterObj.balance__type__in?.forEach(v => {
    chips.push({ key: `${side}:type:${v}`, label: `${sideLabel} ${t('filter_transactions.system')}: ${v}` })
  })
}

const activeFilterChips = computed(() => {
  const chips = []
  const f = filters.value

  if (f.searchQueryId)
    chips.push({ key: 'searchQueryId', label: `ID: ${f.searchQueryId}` })
  if (f.searchQueryIn)
    chips.push({ key: 'searchQueryIn', label: `${t('search_in_order')}: ${f.searchQueryIn}` })
  if (f.searchQueryOut)
    chips.push({ key: 'searchQueryOut', label: `${t('search_out_order')}: ${f.searchQueryOut}` })

  f.selectedType?.forEach(type => {
    chips.push({ key: `type:${type}`, label: `${t('type')}: ${type}` })
  })

  if (f.dateRange)
    chips.push({ key: 'dateRange', label: `${t('creation_date_range')}: ${f.dateRange}` })
  if (f.minAmount)
    chips.push({ key: 'minAmount', label: `${t('min_amount_usdt')}: ${f.minAmount}` })
  if (f.maxAmount)
    chips.push({ key: 'maxAmount', label: `${t('max_amount_usdt')}: ${f.maxAmount}` })
  if (f.ordering && f.ordering !== '-creation_date') {
    const orderingLabel = orderingTypes.find(o => o.value === f.ordering)?.name ?? f.ordering
    chips.push({ key: 'ordering', label: `${t('ordering')}: ${orderingLabel}` })
  }

  addPersonFilterChips(chips, 'from', f.from)
  addPersonFilterChips(chips, 'to', f.to)

  return chips
})

const removeFilterChip = key => {
  const f = filters.value
  const scalarKeys = {
    searchQueryId: '',
    searchQueryIn: '',
    searchQueryOut: '',
    dateRange: '',
    minAmount: 0,
    maxAmount: 0,
    ordering: '-creation_date',
  }

  if (key in scalarKeys) {
    f[key] = scalarKeys[key]
  } else if (key.startsWith('type:')) {
    const type = key.slice(5)
    f.selectedType = f.selectedType.filter(item => item !== type)
  } else if (key.startsWith('from:') || key.startsWith('to:')) {
    const parts = key.split(':')
    const side = parts[0]
    const field = parts[1]
    const value = parts.slice(2).join(':')
    const fieldMap = {
      user: 'balance__available__user__username__in',
      merchant: 'balance__available_merchant__user__username__in',
      team: 'balance__available__team__name__in',
      type: 'balance__type__in',
    }
    const filterKey = fieldMap[field]
    if (filterKey) {
      f[side][filterKey] = f[side][filterKey].filter(item => item !== value)
    }
  }

  searchTransactions()
}

const searchTransactions = () => {
  currentPage.value = 1
  getTransactions()
}

const resetFilters = () => {
  const { rowsPerPage } = filters.value
  filters.value = {
    searchQueryId: '',
    rowsPerPage,
    selectedType: [],
    minAmount: 0,
    maxAmount: 0,
    searchQueryIn: '',
    searchQueryOut: '',
    dateRange: '',
    from: structuredClone(toRaw(baseTransactionsFilter)),
    to: structuredClone(toRaw(baseTransactionsFilter)),
    ordering: '-creation_date',
    direction: 'all',
  }
  searchTransactions()
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

    <AccountListLayout
      v-model:filter-panel-expanded="filterPanelExpanded"
      v-model:rows-per-page="filters.rowsPerPage"
      v-model:current-page="currentPage"
      :advanced-filter-count="advancedFilterCount"
      :active-filter-chips="activeFilterChips"
      :rows-per-page-options="rowsPerPageOptions"
      :pagination-data="paginationData"
      :total-page="totalPage"
      @search="searchTransactions"
      @reset="resetFilters"
      @remove-chip="removeFilterChip"
      @clear-all="resetFilters"
      @refresh="getTransactions"
    >
      <template #search-fields>
        <div class="ui-orders-search__field">
          <AppTextField
            v-model="filters.searchQueryId"
            :label="$t('id')"
            density="compact"
            class="ui-field--mono"
            @keydown.enter="searchTransactions"
          />
        </div>
        <div class="ui-orders-search__field">
          <AppTextField
            v-model="filters.searchQueryIn"
            :label="$t('search_in_order')"
            density="compact"
            @keydown.enter="searchTransactions"
          />
        </div>
        <div class="ui-orders-search__field">
          <AppTextField
            v-model="filters.searchQueryOut"
            :label="$t('search_out_order')"
            density="compact"
            @keydown.enter="searchTransactions"
          />
        </div>
      </template>

      <template #filters>
        <UiFilterSection :title="$t('filter_section_status')">
          <VRow dense>
            <VCol cols="12" sm="6" md="4">
              <AppSelect
                v-model="filters.selectedType"
                :label="$t('type')"
                :items="itemTypes"
                item-title="name"
                item-value="value"
                multiple
                clearable
                clear-icon="lucide:x"
                :prepend-inner-icon="filters.selectedType.length === itemTypes.length ? 'lucide:square-check': 'lucide:square'"
                @click:prepend-inner="switchSelection(itemTypes, 'selectedType', 'value')"
              />
            </VCol>
            <VCol cols="12" sm="6" md="4">
              <AppSelect
                v-model="filters.ordering"
                :label="$t('ordering')"
                :items="orderingTypes"
                item-title="name"
                item-value="value"
                clear-icon="lucide:x"
              />
            </VCol>
          </VRow>
        </UiFilterSection>

        <UiFilterSection :title="$t('filter_section_amounts')">
          <VRow dense>
            <VCol cols="12" sm="6" md="4">
              <AppDateTimePicker
                v-model="filters.dateRange"
                :label="$t('creation_date_range')"
                :config="{ mode: 'range' }"
                clearable
                clear-icon="lucide:x"
              />
            </VCol>
            <VCol cols="12" sm="6" md="4">
              <AppTextField
                v-model="filters.minAmount"
                :label="$t('min_amount_usdt')"
                type="number"
                clearable
                clear-icon="lucide:x"
              />
            </VCol>
            <VCol cols="12" sm="6" md="4">
              <AppTextField
                v-model="filters.maxAmount"
                :label="$t('max_amount_usdt')"
                type="number"
                clearable
                clear-icon="lucide:x"
              />
            </VCol>
          </VRow>
        </UiFilterSection>

        <UiFilterSection :title="$t('filter_section_people')">
          <div class="d-flex flex-wrap gap-3">
            <UiButton variant="default" size="small" @click="isUserFilterFromTransactionsDialogOpen = true">
              {{ $t('from_filters') }}
            </UiButton>
            <UiButton variant="default" size="small" @click="isUserFilterToTransactionsDialogOpen = true">
              {{ $t('to_filters') }}
            </UiButton>
          </div>
        </UiFilterSection>
      </template>

      <template #table>
        <UiDataTable>
                <thead>
                  <tr>
                    <th scope="col">
                      {{ $t('type') }}
                    </th>
                    <th scope="col" class="text-end">
                      {{ $t('total') }}
                    </th>
                    <th scope="col">
                      {{ $t('transactions.from') }}
                    </th>
                    <th scope="col">
                      {{ $t('transactions.to') }}
                    </th>
                    <th scope="col">
                      {{ $t('comment') }}
                    </th>
                    <th scope="col">
                      {{ $t('linked_out_order') }}
                    </th>
                    <th scope="col">
                      {{ $t('linked_in_order') }}
                    </th>
                    <th scope="col">
                      {{ $t('date') }}
                    </th>
                    <th scope="col">
                      {{ $t('id') }}
                    </th>
                  </tr>
                </thead>

                <tbody>
                  <tr
                    v-for="(item, index) in items"
                    :key="item.id"
                    :class="{ 'ui-table-row--alt': index % 2 === 0 }"
                  >
                    <td>
                      <UiStatusBadge
                        :color="resolveTransactionTypeVariantAndIcon(item.transaction_type).variant"
                        :icon="resolveTransactionTypeVariantAndIcon(item.transaction_type).icon"
                        :label="resolveTransactionTypeVariantAndIcon(item.transaction_type).text"
                      />
                    </td>

                    <td class="ui-data-table__cell--num">
                      <div class="ui-cell-stack ui-cell-stack--end">
                        <span class="ui-cell-amount">{{ item.value }}</span>
                        <span class="ui-cell-currency">USD · {{ item.is_incoming ? 'In' : 'Out' }}</span>
                      </div>
                    </td>

                    <td class="ui-cell-meta">
                      @{{ item.from }}
                    </td>

                    <td class="ui-cell-meta">
                      @{{ item.to }}
                    </td>

                    <td class="ui-cell-meta">
                      {{ item.comment || '—' }}
                    </td>

                    <td>
                      <VTooltip
                        v-if="item.linked_out_order"
                        location="end"
                      >
                        <template #activator="{ props }">
                          <button
                            type="button"
                            class="ui-copy-id"
                            v-bind="props"
                            @click="copyToClipboard (item.linked_out_order, 'Transaction Linked Out Order copied!', 'success')"
                          >
                            {{ formatUUID (item.linked_out_order) }}
                          </button>
                        </template>
                        <span>{{ item.linked_out_order }}</span>
                      </VTooltip>
                      <span
                        v-else
                        class="ui-cell-meta"
                      >—</span>
                    </td>

                    <td>
                      <VTooltip
                        v-if="item.linked_in_order"
                        location="end"
                      >
                        <template #activator="{ props }">
                          <button
                            type="button"
                            class="ui-copy-id"
                            v-bind="props"
                            @click="copyToClipboard (item.linked_in_order, 'Transaction Linked In Order copied!', 'success')"
                          >
                            {{ formatUUID (item.linked_in_order) }}
                          </button>
                        </template>
                        <span>{{ item.linked_in_order }}</span>
                      </VTooltip>
                      <span
                        v-else
                        class="ui-cell-meta"
                      >—</span>
                    </td>

                    <td class="ui-data-table__cell--date">
                      {{ (new Date (parseInt(item.creation_date) * 1000)).toUTCString () }}
                      <VTooltip activator="parent">
                        <p class="mb-0">
                          {{ $t ('created_at') }}: {{ (new Date (parseInt(item.creation_date) * 1000)).toUTCString () }}
                        </p>
                      </VTooltip>
                    </td>

                    <td>
                      <VTooltip location="end">
                        <template #activator="{ props }">
                          <button
                            type="button"
                            class="ui-copy-id"
                            v-bind="props"
                            @click="copyToClipboard (item.id, 'Transaction ID copied!', 'success')"
                          >
                            {{ formatUUID (item.id) }}
                          </button>
                        </template>
                        <span>{{ item.id }}</span>
                      </VTooltip>
                    </td>
                  </tr>
                </tbody>

                <tfoot v-show="!items || !items.length">
                  <tr>
                    <td
                      colspan="10"
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
      </template>
    </AccountListLayout>

    <FilterTransactions
      v-model:is-dialog-visible="isUserFilterFromTransactionsDialogOpen"
      v-model:data="filters.from"
      type="from"
      @update:data="filters.from = $event"
    />
    <FilterTransactions
      v-model:is-dialog-visible="isUserFilterToTransactionsDialogOpen"
      v-model:data="filters.to"
      type="to"
      @update:data="filters.to = $event"
    />
  </div>
</template>