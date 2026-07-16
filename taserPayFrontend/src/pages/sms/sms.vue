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
  if (filters.value.apply_filters) {
    if (filters.value.searchId)
      params.id = filters.value.searchId
    if (filters.value.selectedStatus && filters.value.selectedStatus.length > 0)
      params.status__in = filters.value.selectedStatus.join (",")

    // Trader Boss Filters (Only)
    if (filters.value.selectedTraders && filters.value.selectedTraders.length > 0)
      params.device__trader__user__username__in = filters.value.selectedTraders.join (",")

    // Support Filters
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
  }

  // END Filters


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

const smsTruthMetrics = computed (() => [
  { label: t ('sms'), value: String (total.value), tone: 'primary' },
])
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

    <ApWorkspace v-if="authStore.is_authenticated()">
      <template #header>
        <ApPageHeader
          :title="t('sms')"
          :subtitle="t('nav.operations')"
        />
      </template>

      <div class="ap-filter-toolbar">
        <VSelect
          v-model="filters.rowsPerPage"
          :items="rowsPerPageOptions"
          :label="$t('rows')"
          item-title="name"
          item-value="value"
          scroll-strategy="close"
          color="primary"
          density="compact"
          hide-details
          style="max-width: 7rem;"
        />
        <VBtn
          icon="tabler-refresh"
          size="small"
          variant="tonal"
          @click="getSms"
        />
      </div>

      <ApFilterPanel class="mb-3">
        <VRow>
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
              :item-title="option => $t (`sms_status.${option.value.toLowerCase()}`)"
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
          <VCol
            cols="12"
            sm="6"
          >
            <AppDateTimePicker
              v-model="filters.dateRange"
              :label="$t('creation_date_range')"
              :config="{ mode: 'range' }"
              clearable
              clear-icon="tabler-x"
            />
          </VCol>
        </VRow>

        <div
          v-if="authStore.is_support() || authStore.is_senior_trader()"
          class="ap-section"
        >
          <VRow>
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
        </div>
      </ApFilterPanel>

      <ApTruthStrip :items="smsTruthMetrics" />

      <ApActionZone sticky>
        <template #leading>
          <VSwitch
            v-model="filters.apply_filters"
            :label="filters.apply_filters ? $t('apply_filters') : $t('not_apply_filters')"
            hide-details
            density="compact"
            @change="getSms"
          />
        </template>
        <div style="inline-size: 10rem;">
          <AppTextField
            v-model="filters.searchId"
            :placeholder="$t('id')"
            density="compact"
            hide-details
          />
        </div>
        <div style="inline-size: 10rem;">
          <AppTextField
            v-model="filters.searchDevice"
            :placeholder="$t('device')"
            density="compact"
            hide-details
          />
        </div>
        <div style="inline-size: 10rem;">
          <AppTextField
            v-model="filters.searchText"
            :placeholder="$t('text')"
            density="compact"
            hide-details
          />
        </div>
        <div style="inline-size: 10rem;">
          <AppTextField
            v-model="filters.searchDeviceOwner"
            :placeholder="$t('device_owner')"
            density="compact"
            hide-details
          />
        </div>
        <div style="inline-size: 10rem;">
          <AppTextField
            v-model="filters.searchInOrder"
            :placeholder="$t('search_in_order')"
            density="compact"
            hide-details
          />
        </div>
        <div style="inline-size: 10rem;">
          <AppTextField
            v-model="filters.searchOutOrder"
            :placeholder="$t('search_out_order')"
            density="compact"
            hide-details
          />
        </div>
        <VBtn
          variant="tonal"
          color="secondary"
          prepend-icon="tabler-screen-share"
        >
          {{ $t ('export') }}
        </VBtn>
        <VBtn
          color="primary"
          prepend-icon="tabler-search"
          @click="getSms"
        >
          {{ $t ('search') }}
        </VBtn>
      </ApActionZone>

      <ApDataGrid class="text-body-2">
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
                    :class="index % 2 === 0 ? 'bg-light-secondary': ''"
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
      </ApDataGrid>

      <template #footer>
        <div class="d-flex align-center flex-wrap justify-space-between gap-4 w-100">
          <span class="text-sm text-disabled">{{ paginationData }}</span>
          <VPagination
            v-model="currentPage"
            size="small"
            :total-visible="5"
            :length="totalPage"
            @next="selectedRows = []"
            @prev="selectedRows = []"
          />
        </div>
      </template>
    </ApWorkspace>
  </div>
</template>
