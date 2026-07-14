<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { useTradeStore } from "@/stores/useTradeStore"
import { useBaseStore } from "@/stores/useBaseStore"
import { formatUUID, resolveWithdrawalStatusVariantAndIcon } from "@core/utils/formatters"

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
    <VRow>
      <VCol cols="12">
        <VCard>
          <VCardTitle class="mt-2 ms-2">
            <VAvatar
              size="50"
              variant="text"
              color="primary"
              icon="tabler-stack-pop"
            />
            {{ t ('tabs.withdrawals') }}
          </VCardTitle>
          <VCol cols="12">
            <VCard>
              <VCardText class="d-flex align-center flex-wrap gap-3">
                <VCardText
                  class="text-h5 mb-0"
                  style="padding: 0.5rem;"
                >
                  {{ t ('tabs.withdrawals') }}
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
                <VBtn
                  icon="tabler-refresh"
                  size="small"
                  @click="getWithdrawals"
                />
              </VCardText>

              <VCardText>
                <VRow>
                  <!-- 👉 Select Role -->
                  <VCol
                    cols="12"
                    sm="4"
                    md="3"
                  >
                    <AppSelect
                      v-model="filters.selectedType"
                      :label="$t('type')"
                      :items="itemTypes"
                      item-title="name"
                      item-value="value"
                      multiple
                      clearable
                      clear-icon="tabler-x"
                      :prepend-inner-icon="filters.selectedType.length === itemTypes.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                      @click:prependInner="switchSelection(itemTypes, 'selectedType', 'value')"
                    />
                  </VCol>
                  <!-- 👉 Select Plan -->
                  <VCol
                    v-if="authStore.is_support()"
                    cols="12"
                    sm="4"
                    md="3"
                  >
                    <AppSelect
                      v-model="filters.selectedTarget"
                      :label="$t('from_user')"
                      :items="withdrawalTargets"
                      item-title="name"
                      item-value="name"
                      multiple
                      clearable
                      clear-icon="tabler-x"
                      :prepend-inner-icon="filters.selectedTarget.length === withdrawalTargets.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                      @click:prepend-inner="switchSelection(withdrawalTargets, 'selectedTarget', 'name')"
                    />
                  </VCol>
                  <!-- 👉 Select Status -->
                  <VCol
                    cols="12"
                    sm="4"
                    md="2"
                  >
                    <AppTextField
                      v-model="filters.minAmount"
                      :label="$t('min_amount_usdt')"
                      type="number"
                      clearable
                      clear-icon="tabler-x"
                    />
                  </VCol>
                  <VCol
                    cols="12"
                    sm="4"
                    md="2"
                  >
                    <AppTextField
                      v-model="filters.maxAmount"
                      :label="$t('max_amount_usdt')"
                      type="number"
                      clearable
                      clear-icon="tabler-x"
                    />
                  </VCol>
                  <VCol
                    cols="12"
                    sm="4"
                    md="2"
                  >
                    <AppSelect
                      v-model="filters.ordering"
                      :label="$t('ordering')"
                      :items="orderingTypes"
                      item-title="name"
                      item-value="value"
                      clear-icon="tabler-x"
                    />
                  </VCol>
                </VRow>
              </VCardText>

              <VDivider />

              <VCardText class="d-flex flex-wrap py-4 gap-4">
                <VSpacer />
                <div class="app-user-search-filter d-flex align-center flex-wrap gap-4">
                  <div style="inline-size: 15rem;">
                    <AppDateTimePicker
                      v-model="filters.dateRange"
                      :placeholder="$t('creation_date_range')"
                      :config="{ mode: 'range' }"
                    />
                  </div>
                  <div style="inline-size: 10rem;">
                    <AppTextField
                      v-model="filters.searchQueryId"
                      :placeholder="$t('id')"
                      density="compact"
                    />
                  </div>
                  <div style="inline-size: 10rem;">
                    <AppTextField
                      v-model="filters.searchQueryComment"
                      :placeholder="$t('search_comment')"
                      density="compact"
                    />
                  </div>
                  <div style="inline-size: 10rem;">
                    <AppTextField
                      v-model="filters.searchQueryAddress"
                      :placeholder="$t('search_address')"
                      density="compact"
                    />
                  </div>
                  <VBtn
                    variant="tonal"
                    color="secondary"
                    prepend-icon="tabler-screen-share"
                  >
                    {{ $t('export') }}
                  </VBtn>
                  <VBtn
                    color="primary"
                    prepend-icon="tabler-search"
                    @click="getWithdrawals"
                  >
                    {{ $t('search') }}
                  </VBtn>
                </div>
              </VCardText>

              <VDivider />
              <!-- SECTION Table -->
              <VTable class="text-no-wrap invoice-list-table">
                <!-- 👉 Table head -->
                <thead>
                  <tr>
                    <th scope="col">
                      {{ $t ('id').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('status').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('amount').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('address_to').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('comment').toUpperCase () }}
                    </th>
                    <th scope="col">
                      {{ $t ('date').toUpperCase () }}
                    </th>
                  </tr>
                </thead>

                <tbody>
                  <tr
                    v-for="item in items"
                    :key="item.id"
                  >
                    <td>
                      <VTooltip
                        location="end"
                      >
                        <template #activator="{ props }">
                          <VBtn
                            variant="text"
                            v-bind="props"
                            @click="copyToClipboard (item.id, 'Request ID copied!', 'success')"
                          >
                            {{ formatUUID (item.id) }}
                          </VBtn>
                        </template>
                        <span>
                          {{ item.id }}
                        </span>
                      </VTooltip>
                    </td>

                    <td>
                      <VTooltip>
                        <template #activator="{ props }">
                          <VAvatar
                            :size="30"
                            v-bind="props"
                            :color="resolveWithdrawalStatusVariantAndIcon(item.status).variant"
                            variant="tonal"
                          >
                            <VIcon
                              :size="20"
                              :icon="resolveWithdrawalStatusVariantAndIcon(item.status).icon"
                            />
                          </VAvatar>
                        </template>
                        <p class="mb-0">
                          {{ resolveWithdrawalStatusVariantAndIcon (item.status).text }}
                        </p>
                      </vtooltip>
                    </td>

                    <td>
                      USD&nbsp;{{ item.amount }}
                    </td>
                    <td>
                      {{ item.address_to }}
                    </td>
                    <td>
                      {{ item.comment }}
                    </td>
                    <td>
                      {{ (new Date (parseInt(item.date) * 1000)).toUTCString () }}
                      <VTooltip activator="parent">
                        <p class="mb-0">
                          {{ $t ('created_at') }}: {{ (new Date (parseInt(item.date) * 1000)).toUTCString () }}
                        </p>
                      </VTooltip>
                    </td>
                  </tr>
                </tbody>

                <!-- 👉 table footer  -->

                <tfoot v-show="!items || !items.length">
                  <tr>
                    <td
                      colspan="8"
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
                      colspan="8"
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
      </VCol>
    </VRow>
  </div>
</template>
