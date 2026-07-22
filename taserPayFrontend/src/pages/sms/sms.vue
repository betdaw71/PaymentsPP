<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { useTradeStore } from "@/stores/useTradeStore"
import {
  capitalize,
  formatUUID,
  resolveSmsStatusVariantAndIcon,
  formatTimeDelta, formatTimeDeltaSeconds,
} from "@core/utils/formatters"
import { useBaseStore } from "@/stores/useBaseStore"
import ViewPaymentDetailsDrawer from "@/views/user/ViewPaymentDetailsDrawer.vue"
import AddPaymentDetailsDrawer from "@/views/user/AddPaymentDetailsDrawer.vue"
import { useSmsStore } from "@/stores/useSmsStore"

const { t } = useI18n ()
const tradeStore = useTradeStore ()
const authStore = useAuthStore ()
const baseStore = useBaseStore ()
const smsStore = useSmsStore ()

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
  structuredClone (toRaw (smsStore.sms_filters)),
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
    value: "-date",
    name: "Date (Desc)",
  },
  {
    value: "date",
    name: "Date (Asc)",
  },
]

const rowsPerPageOptions = [
  { value: 10, name: "x10" },
  { value: 20, name: "x20" },
  { value: 50, name: "x50" },
]

const getFilters = async () => {
  smsStore.getFiltersSms ({}).then (
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

const getSms = async () => {
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
  if (filters.value.searchId)
    params.id = filters.value.searchId
  if (filters.value.selectedStatus && filters.value.selectedStatus.length > 0)
    params.status__in = filters.value.selectedStatus.join (",")
  if (filters.value.selectedTraders && filters.value.selectedTraders.length > 0)
    params.device__trader__user__username__in = filters.value.selectedTraders.join (",")
  if (filters.value.selectedTeams && filters.value.selectedTeams.length > 0)
    params.device__trader__team__name__in = filters.value.selectedTeams.join (",")
  if (filters.value.searchDevice)
    params.device = filters.value.searchDevice
  if (filters.value.searchText)
    params.text__icontains = filters.value.searchText
  if (filters.value.searchDeviceOwner)
    params.device__owner = filters.value.searchDeviceOwner
  if (filters.value.searchInOrder)
    params.inorder = filters.value.searchInOrder
  if (filters.value.searchOutOrder)
    params.outorder = filters.value.searchOutOrder
  if (filters.value.dateRange && filters.value.dateRange.includes (" to "))
    params.date__range = filters.value.dateRange.replace (" to ", ",")


  smsStore.getSms (params).then (response => {
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
    getSms ()
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
    getSms ()
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
    smsStore.sms_filters = structuredClone (toRaw (filters.value))
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
  baseStore.changePaymentDetailsDirectionStatusById (data, item.id).then (response => {
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
  if (f.searchDevice) n++
  if (f.searchDeviceOwner) n++
  if (f.searchInOrder) n++
  if (f.searchOutOrder) n++
  if (f.dateRange) n++
  if (f.selectedStatus?.length) n++
  if (f.selectedTraders?.length) n++
  if (f.selectedTeams?.length) n++
  if (f.ordering && f.ordering !== '-date') n++
  return n
}

const advancedFilterCount = computed(() => countAdvancedFilters(filters.value))

const activeFilterChips = computed(() => {
  const chips = []
  const f = filters.value

  if (f.searchId)
    chips.push({ key: 'searchId', label: `ID: ${f.searchId}` })
  if (f.searchText)
    chips.push({ key: 'searchText', label: `${t('text')}: ${f.searchText}` })
  if (f.searchDevice)
    chips.push({ key: 'searchDevice', label: `${t('device')}: ${f.searchDevice}` })
  if (f.searchDeviceOwner)
    chips.push({ key: 'searchDeviceOwner', label: `${t('device_owner')}: ${f.searchDeviceOwner}` })
  if (f.searchInOrder)
    chips.push({ key: 'searchInOrder', label: `${t('search_in_order')}: ${f.searchInOrder}` })
  if (f.searchOutOrder)
    chips.push({ key: 'searchOutOrder', label: `${t('search_out_order')}: ${f.searchOutOrder}` })
  if (f.dateRange)
    chips.push({ key: 'dateRange', label: `${t('creation_date_range')}: ${f.dateRange}` })

  f.selectedStatus?.forEach(status => {
    chips.push({
      key: `status:${status}`,
      label: `${t('status')}: ${t(`sms_status.${status.toLowerCase()}`)}`,
    })
  })
  f.selectedTraders?.forEach(tr => {
    chips.push({ key: `trader:${tr}`, label: `${t('traders')}: ${tr}` })
  })
  f.selectedTeams?.forEach(team => {
    chips.push({ key: `team:${team}`, label: `${t('teams')}: ${team}` })
  })

  if (f.ordering && f.ordering !== '-date') {
    const orderingLabel = orderingTypes.find(o => o.value === f.ordering)?.name ?? f.ordering
    chips.push({ key: 'ordering', label: `${t('ordering')}: ${orderingLabel}` })
  }

  return chips
})

const removeFilterChip = key => {
  const f = filters.value
  const scalarKeys = {
    searchId: '',
    searchText: '',
    searchDevice: '',
    searchDeviceOwner: '',
    searchInOrder: '',
    searchOutOrder: '',
    dateRange: '',
    ordering: '-date',
  }

  if (key in scalarKeys) {
    f[key] = scalarKeys[key]
  } else if (key.startsWith('status:')) {
    const status = key.slice(7)
    f.selectedStatus = f.selectedStatus.filter(s => s !== status)
  } else if (key.startsWith('trader:')) {
    f.selectedTraders = f.selectedTraders.filter(s => s !== key.slice(7))
  } else if (key.startsWith('team:')) {
    f.selectedTeams = f.selectedTeams.filter(s => s !== key.slice(5))
  }

  searchSms()
}

const toggleFilterPanel = () => {
  filterPanelExpanded.value = !filterPanelExpanded.value
}

const searchSms = () => {
  currentPage.value = 1
  getSms()
}

const resetFilters = () => {
  const { rowsPerPage } = filters.value
  filters.value = {
    searchId: '',
    searchText: '',
    rowsPerPage,
    searchDevice: '',
    searchDeviceOwner: '',
    searchInOrder: '',
    searchOutOrder: '',
    selectedStatus: [],
    selectedTraders: [],
    selectedTeams: [],
    dateRange: '',
    ordering: '-date',
  }
  searchSms()
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
            icon="lucide:smartphone"
          />
          <h1 class="ui-workspace__title">
            {{ t('sms') }}
          </h1>
        </div>
      </template>
      <template #actions>
        <UiButton
          variant="ghost"
          size="small"
          icon
          @click="getSms"
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
              v-model="filters.searchId"
              :label="$t('id')"
              density="compact"
              class="ui-field--mono"
              @keydown.enter="searchSms"
            />
          </div>
          <div class="ui-orders-search__field">
            <AppTextField
              v-model="filters.searchText"
              :label="$t('text')"
              density="compact"
              @keydown.enter="searchSms"
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
            @click="searchSms"
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
          @apply="searchSms"
          @reset="resetFilters"
        >
          <UiFilterSection :title="$t('filter_section_identifiers')">
            <VRow dense>
              <VCol
                cols="12"
                sm="6"
                md="4"
              >
                <AppTextField
                  v-model="filters.searchDevice"
                  :label="$t('device')"
                  density="compact"
                />
              </VCol>
              <VCol
                cols="12"
                sm="6"
                md="4"
              >
                <AppTextField
                  v-model="filters.searchDeviceOwner"
                  :label="$t('device_owner')"
                  density="compact"
                />
              </VCol>
              <VCol
                cols="12"
                sm="6"
                md="4"
              >
                <AppTextField
                  v-model="filters.searchInOrder"
                  :label="$t('search_in_order')"
                  density="compact"
                />
              </VCol>
              <VCol
                cols="12"
                sm="6"
                md="4"
              >
                <AppTextField
                  v-model="filters.searchOutOrder"
                  :label="$t('search_out_order')"
                  density="compact"
                />
              </VCol>
            </VRow>
          </UiFilterSection>

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
                  :item-title="option => $t(`sms_status.${option.value.toLowerCase()}`)"
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

          <UiFilterSection :title="$t('filter_section_amounts')">
            <VRow dense>
              <VCol
                cols="12"
                sm="6"
                md="4"
              >
                <AppDateTimePicker
                  v-model="filters.dateRange"
                  :placeholder="$t('creation_date_range')"
                  :config="{ mode: 'range' }"
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
                      {{ $t ('device').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('date').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('text').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('order_in').toUpperCase () }}
                    </th>
                    <th
                      class="text-wrap"
                      scope="col"
                    >
                      {{ $t ('order_out').toUpperCase () }}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(item, index) in items"
                    :key="item.id"
                    class="cursor-pointer"
                    :class="{ 'ui-table-row--alt': index % 2 === 0 }"
                  >
                    <td>
                      <VChip
                        size="small"
                        :color="resolveSmsStatusVariantAndIcon(item.status).variant"
                        variant="tonal"
                        :prepend-icon="resolveSmsStatusVariantAndIcon(item.status).icon"
                      >
                        {{ resolveSmsStatusVariantAndIcon (item.status).text }}
                      </VChip>
                    </td>
                    <td>
                      {{ item.device }}
                    </td>
                    <td>
                      {{ (new Date (parseInt (item.date) * 1000)).toUTCString () }}
                      <VTooltip activator="parent">
                        <p class="mb-0">
                          {{ $t ('date') }}: {{ (new Date (parseInt (item.date) * 1000)).toUTCString () }}
                        </p>
                      </VTooltip>
                    </td>
                    <td>
                      {{ item.text }}
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
                            @click.stop="copyToClipboard (item.order_in, 'In Order ID copied!', 'success')"
                          >
                            {{ formatUUID (item.order_in) }}
                          </VBtn>
                        </template>
                        <span>
                          {{ item.order_in }}
                        </span>
                      </VTooltip>
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
                            @click.stop="copyToClipboard (item.order_out, 'Out Order ID copied!', 'success')"
                          >
                            {{ formatUUID (item.order_out) }}
                          </VBtn>
                        </template>
                        <span>
                          {{ item.order_out }}
                        </span>
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
  </div>
</template>
