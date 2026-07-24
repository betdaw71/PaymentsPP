<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { useTradeStore } from "@/stores/useTradeStore"
import { useBaseStore } from "@/stores/useBaseStore"
import { formatUUID, resolveWithdrawalStatusVariantAndIcon } from "@core/utils/formatters"
import WithdrawalRejectDialog from "@/views/user/WithdrawalRejectDialog.vue"
import WithdrawalApproveDialog from "@/views/user/WithdrawalApproveDialog.vue"

const { t } = useI18n ()
const tradeStore = useTradeStore ()
const authStore = useAuthStore ()
const baseStore = useBaseStore ()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const searchQuery = ref ('')
const selectedStatus = ref ()

const currentPage = ref (1)
const totalPage = ref (1)
const total = ref (0)
const items = ref ([])
const selectedRows = ref ([])
const isRejectWithdrawalDialogOpen = ref (false)
const isApproveWithdrawalDialogOpen = ref (false)

const filters = ref (
  structuredClone (toRaw (baseStore.withdrawals_filters)),
)

const rowsPerPageOptions = [
  { value: 10, name: "x10" },
  { value: 20, name: "x20" },
  { value: 50, name: "x50" },
]

const withdrawalItem = ref ({
  "id": "",
  "from_user": "",
  "amount": 0,
})

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

const withdrawalTargets = ref([])

const getWithdrawalTargets = async () => {
  loadMessage.value = {
    message: t ('data.loading'),
    status: 0,
  }
  withdrawalTargets.value = []
  baseStore.getWithdrawalTargets ({}).then (response => {
    if (response.error)
      throw response.error
    withdrawalTargets.value = response.data.users
    console.log({
      targets: withdrawalTargets.value,
    })
  }).catch (error => {
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
  })
}

const itemTypes = [
  { value: 0, name: "New" },
  { value: 1, name: "Success" },
  { value: 2, name: "Rejected" },
]

const orderingTypes = [
  {
    value: "-date",
    name: "Date (Desc)",
  },
  {
    value: "date",
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
    value: "-status",
    name: "Status (Desc)",
  },
  {
    value: "status",
    name: "Status (Asc)",
  },
]

const getWithdrawals = async () => {
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
  if (filters.value.searchQueryId)
    params.id = filters.value.searchQueryId
  if (filters.value.searchQueryAddress)
    params.address_to = filters.value.searchQueryAddress
  if (filters.value.searchQueryComment)
    params.comment = filters.value.searchQueryComment
  if (filters.value.selectedType && filters.value.selectedType.length > 0)
    params.status__in = filters.value.selectedType.join (",")
  if (filters.value.minAmount)
    params.amount__gte = filters.value.minAmount
  if (filters.value.maxAmount)
    params.amount__lte = filters.value.maxAmount
  if (filters.value.dateRange && filters.value.dateRange.includes (" to "))
    params.date__range = filters.value.dateRange.replace (" to ", ",")
  if(filters.value.selectedTarget && filters.value.selectedTarget.length > 0)
    params.from_user__username = filters.value.selectedTarget.join (",")
  tradeStore.getTradeWithdrawalRequest (params).then (response => {
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
    getWithdrawals ()
  },
  { deep: true },
)
onMounted(
  () => {

    if(authStore.is_support())
      getWithdrawalTargets()
    getWithdrawals ()
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
    baseStore.withdrawals_filters = structuredClone (toRaw (filters.value))
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

const countAdvancedFilters = f => {
  let n = 0
  if (f.selectedType?.length) n++
  if (f.selectedTarget?.length) n++
  if (f.minAmount) n++
  if (f.maxAmount) n++
  if (f.dateRange) n++
  if (f.ordering && f.ordering !== '-date') n++
  return n
}

const advancedFilterCount = computed(() => countAdvancedFilters(filters.value))

const activeFilterChips = computed(() => {
  const chips = []
  const f = filters.value

  if (f.searchQueryId)
    chips.push({ key: 'searchQueryId', label: `ID: ${f.searchQueryId}` })
  if (f.searchQueryComment)
    chips.push({ key: 'searchQueryComment', label: `${t('search_comment')}: ${f.searchQueryComment}` })
  if (f.searchQueryAddress)
    chips.push({ key: 'searchQueryAddress', label: `${t('search_address')}: ${f.searchQueryAddress}` })

  f.selectedType?.forEach(type => {
    const typeName = itemTypes.find(i => i.value === type)?.name ?? type
    chips.push({ key: `type:${type}`, label: `${t('type')}: ${typeName}` })
  })

  f.selectedTarget?.forEach(target => {
    chips.push({ key: `target:${target}`, label: `${t('from_user')}: ${target}` })
  })

  if (f.dateRange)
    chips.push({ key: 'dateRange', label: `${t('creation_date_range')}: ${f.dateRange}` })
  if (f.minAmount)
    chips.push({ key: 'minAmount', label: `${t('min_amount_usdt')}: ${f.minAmount}` })
  if (f.maxAmount)
    chips.push({ key: 'maxAmount', label: `${t('max_amount_usdt')}: ${f.maxAmount}` })
  if (f.ordering && f.ordering !== '-date') {
    const orderingLabel = orderingTypes.find(o => o.value === f.ordering)?.name ?? f.ordering
    chips.push({ key: 'ordering', label: `${t('ordering')}: ${orderingLabel}` })
  }

  return chips
})

const removeFilterChip = key => {
  const f = filters.value
  const scalarKeys = {
    searchQueryId: '',
    searchQueryComment: '',
    searchQueryAddress: '',
    dateRange: '',
    minAmount: 0,
    maxAmount: 0,
    ordering: '-date',
  }

  if (key in scalarKeys) {
    f[key] = scalarKeys[key]
  } else if (key.startsWith('type:')) {
    const type = parseInt(key.slice(5), 10)
    f.selectedType = f.selectedType.filter(item => item !== type)
  } else if (key.startsWith('target:')) {
    const target = key.slice(7)
    f.selectedTarget = f.selectedTarget.filter(item => item !== target)
  }

  searchWithdrawals()
}

const searchWithdrawals = () => {
  currentPage.value = 1
  getWithdrawals()
}

const resetFilters = () => {
  const { rowsPerPage } = filters.value
  filters.value = {
    searchQueryId: '',
    rowsPerPage,
    selectedType: [],
    minAmount: 0,
    maxAmount: 0,
    searchQueryComment: '',
    searchQueryAddress: '',
    dateRange: '',
    selectedTarget: [],
    ordering: '-date',
  }
  searchWithdrawals()
}


const approveWithdrawal = item => {
  isApproveWithdrawalDialogOpen.value = true
  withdrawalItem.value = structuredClone (toRaw (item))
}

const rejectWithdrawal = item => {
  isRejectWithdrawalDialogOpen.value = true
  withdrawalItem.value = structuredClone (toRaw (item))
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
      @search="searchWithdrawals"
      @reset="resetFilters"
      @remove-chip="removeFilterChip"
      @clear-all="resetFilters"
      @refresh="getWithdrawals"
    >
      <template #search-fields>
        <div class="ui-orders-search__field">
          <AppTextField
            v-model="filters.searchQueryId"
            :label="$t('id')"
            density="compact"
            class="ui-field--mono"
            @keydown.enter="searchWithdrawals"
          />
        </div>
        <div class="ui-orders-search__field">
          <AppTextField
            v-model="filters.searchQueryComment"
            :label="$t('search_comment')"
            density="compact"
            @keydown.enter="searchWithdrawals"
          />
        </div>
        <div class="ui-orders-search__field">
          <AppTextField
            v-model="filters.searchQueryAddress"
            :label="$t('search_address')"
            density="compact"
            @keydown.enter="searchWithdrawals"
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
            <VCol v-if="authStore.is_support()" cols="12" sm="6" md="4">
              <AppSelect
                v-model="filters.selectedTarget"
                :label="$t('from_user')"
                :items="withdrawalTargets"
                item-title="name"
                item-value="name"
                multiple
                clearable
                clear-icon="lucide:x"
                :prepend-inner-icon="filters.selectedTarget.length === withdrawalTargets.length ? 'lucide:square-check': 'lucide:square'"
                @click:prepend-inner="switchSelection(withdrawalTargets, 'selectedTarget', 'name')"
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
      </template>

      <template #table>
        <UiDataTable>
                <thead>
                  <tr>
                    <th scope="col">
                      {{ $t('withdrawals.actions') }}
                    </th>
                    <th scope="col">
                      {{ $t('withdrawals.status') }}
                    </th>
                    <th scope="col">
                      {{ $t('withdrawals.from_user') }}
                    </th>
                    <th scope="col" class="text-end">
                      {{ $t('withdrawals.amount') }}
                    </th>
                    <th scope="col">
                      {{ $t('withdrawals.address_to') }}
                    </th>
                    <th scope="col">
                      {{ $t('withdrawals.comment') }}
                    </th>
                    <th scope="col">
                      {{ $t('withdrawals.date') }}
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
                      <div class="d-flex align-center gap-1">
                        <template v-if="item.status === 0">
                          <VTooltip location="end">
                            <template #activator="{ props }">
                              <VBtn
                                v-bind="props"
                                size="x-small"
                                color="success"
                                variant="flat"
                                icon="lucide:circle-check"
                                @click="approveWithdrawal (item)"
                              />
                            </template>
                            <span>{{ $t('approve') }}</span>
                          </VTooltip>
                          <VTooltip location="end">
                            <template #activator="{ props }">
                              <VBtn
                                v-bind="props"
                                size="x-small"
                                color="error"
                                variant="flat"
                                icon="lucide:circle-x"
                                @click="rejectWithdrawal (item)"
                              />
                            </template>
                            <span>{{ $t('reject') }}</span>
                          </VTooltip>
                        </template>
                        <span
                          v-else
                          class="ui-cell-meta"
                        >{{ $t('no_actions') }}</span>
                      </div>
                    </td>
                    <td>
                      <VChip
                            size="small"
                            :color="resolveWithdrawalStatusVariantAndIcon(item.status).variant"
                            variant="tonal"
                            :prepend-icon="resolveWithdrawalStatusVariantAndIcon(item.status).icon"
                          >
                            {{ resolveWithdrawalStatusVariantAndIcon(item.status).text }}
                          </VChip>
                    </td>
                    <td class="ui-cell-meta">
                      @{{ item.from_user }}
                    </td>
                    <td class="ui-data-table__cell--num">
                      <span class="ui-cell-amount">{{ item.amount }}</span>
                      <span class="ui-cell-currency">USD</span>
                    </td>
                    <td class="ui-cell-meta">
                      {{ item.address_to }}
                    </td>
                    <td class="ui-cell-meta">
                      {{ item.comment || '—' }}
                    </td>
                    <td class="ui-data-table__cell--date">
                      {{ (new Date (parseInt (item.date) * 1000)).toUTCString () }}
                      <VTooltip activator="parent">
                        <p class="mb-0">
                          {{ $t ('created_at') }}: {{ (new Date (parseInt (item.date) * 1000)).toUTCString () }}
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
                            @click="copyToClipboard (item.id, 'Request ID copied!', 'success')"
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
                      colspan="8"
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

    <WithdrawalRejectDialog
      v-model:is-dialog-visible="isRejectWithdrawalDialogOpen"
      :withdrawal-data="withdrawalItem"
    />
    <WithdrawalApproveDialog
      v-model:is-dialog-visible="isApproveWithdrawalDialogOpen"
      :withdrawal-data="withdrawalItem"
    />
  </div>
</template>