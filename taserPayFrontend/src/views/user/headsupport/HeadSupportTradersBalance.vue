<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { useTradeStore } from "@/stores/useTradeStore"
import { formatUUID, resolveTransactionTypeVariantAndIcon } from "@core/utils/formatters"
import { useBaseStore } from "@/stores/useBaseStore"

const { t } = useI18n ()
const tradeStore = useTradeStore ()
const baseStore = useBaseStore ()
const authStore = useAuthStore ()

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
const tab_settings = ref (structuredClone (toRaw (baseStore.balance_settings)))

const defaultData = {
  total_amount: 0,
  total_frozen: 0,
  data: [],
}

const data = ref (structuredClone (toRaw (defaultData)))

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

watch (
  () => tab_settings.value,
  () => {
    baseStore.balance_settings = structuredClone (toRaw (tab_settings.value))
    console.log ({
      currentTeam: tab_settings.value.team_tab,
      currentCurrency: tab_settings.value.currency_tab,
    })
  },
  { deep: true },
)

const getBalances = async () => {
  loadMessage.value = {
    message: t ('data.loading'),
    status: 0,
  }
  data.value = structuredClone (toRaw (defaultData))
  baseStore.getBalances ({}).then (response => {
    if (response.error) {
      throw response.error
    }
    data.value = response.data
    if (data.value.data.length && !tab_settings.value.currency_tab) {
      console.log({ cur_tab: tab_settings.value.currency_tab, team_tab:  tab_settings.value.team_tab })
      tab_settings.value.currency_tab = 0
      if (data.value.data[0].data.length && !tab_settings.value.team_tab) {
        tab_settings.value.team_tab = 0
      }
    }
  }).catch (error => {
    snackbar.value = {
      enabled: true,
      type: "error",
      message: `Error occurred: ${error}`,
    }
    console.log (error)
  })
}

watchEffect (() => {
  getBalances ()
})

watchEffect (() => {
  if (currentPage.value > totalPage.value)
    currentPage.value = totalPage.value
})
watch (
  () => tab_settings.value.currency_tab,
  () => {
    if (data.value.data.length && data.value.data[tab_settings.value.currency_tab].data.length && !tab_settings.value.team_tab) {
      tab_settings.value.team_tab = 0
    }
  },
)
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
              icon="tabler-coin"
            />
            {{ t ('tabs.total_balance') }}
          </VCardTitle>
          <VCol cols="12">
            <VCard>
              <VCardText class="d-flex align-center flex-wrap gap-3">
                <VCardText
                  class="text-h5 mb-0"
                  style="padding: 0.5rem;"
                >
                  {{ t ('tabs.total_balance') }}

                  <VTooltip
                    location="right"
                  >
                    <template #activator="{ props }">
                      <VChip
                        v-bind="props"
                        class="ms-1 p-1 font-weight-bold"
                        color="success"
                        text-color="white"
                        small
                      >
                        $ {{ data.total_amount }}
                      </VChip>
                    </template>
                    <span>
                      {{ $t ('total_available_balance') }}
                    </span>
                  </VTooltip>
                  <VTooltip
                    location="right"
                  >
                    <template #activator="{ props }">
                      <VChip
                        v-bind="props"
                        class="ms-1 p-1 font-weight-bold"
                        color="info"
                        text-color="white"
                        small
                        append-icon="tabler-snowflake"
                      >
                        $ {{ data.total_frozen }}
                      </VChip>
                    </template>
                    <span>
                      {{ $t ('total_frozen_balance') }}
                    </span>
                  </VTooltip>
                </VCardText>

                <VSpacer />
                <VBtn
                  icon="tabler-refresh"
                  size="small"
                  @click="getBalances"
                />
              </VCardText>
              <VCard>
                <VTabs
                  v-model="tab_settings.currency_tab"
                  show-arrows
                >
                  <VTab
                    v-for="item in data.data"
                    :key="item.currency"
                  >
                    {{ item.currency }}
                    <VTooltip
                      location="right"
                    >
                      <template #activator="{ props }">
                        <VChip
                          v-bind="props"
                          class="ms-1 p-1 font-weight-bold"
                          color="success"
                          text-color="white"
                          small
                        >
                          $ {{ item.total_amount }}
                        </VChip>
                      </template>
                      <span>
                        {{ item.currency }} {{ $t ('available_balance') }}
                      </span>
                    </VTooltip>
                    <VTooltip
                      location="right"
                    >
                      <template #activator="{ props }">
                        <VChip
                          v-bind="props"
                          class="ms-1 p-1 font-weight-bold"
                          color="info"
                          text-color="white"
                          small
                          append-icon="tabler-snowflake"
                        >
                          $ {{ item.total_frozen }}
                        </VChip>
                      </template>
                      <span>
                        {{ item.currency }} {{ $t ('frozen_balance') }}
                      </span>
                    </VTooltip>
                  </VTab>
                </VTabs>

                <VCardText>
                  <VWindow v-model="tab_settings.currency_tab">
                    <VWindowItem
                      v-for="item in data.data"
                      :key="item.currency"
                    >
                      <VTabs
                        v-model="tab_settings.team_tab"
                        show-arrows
                      >
                        <VTab
                          v-for="team in item.data"
                          :key="team.team_name"
                        >
                          {{ team.team_name }}
                          <VTooltip
                            location="right"
                          >
                            <template #activator="{ props }">
                              <VChip
                                v-bind="props"
                                class="ms-1 p-1 font-weight-bold"
                                color="success"
                                text-color="white"
                                small
                              >
                                $ {{ team.total_amount }}
                              </VChip>
                            </template>
                            <span>
                              {{ team.team_name }} {{ $t ('available_balance') }}
                            </span>
                          </VTooltip>
                          <VTooltip
                            location="right"
                          >
                            <template #activator="{ props }">
                              <VChip
                                v-bind="props"
                                class="ms-1 p-1 font-weight-bold"
                                color="info"
                                text-color="white"
                                small
                                append-icon="tabler-snowflake"
                              >
                                $ {{ team.total_frozen }}
                              </VChip>
                            </template>
                            <span>
                              {{ team.team_name }} {{ $t ('frozen_balance') }}
                            </span>
                          </VTooltip>
                          <VTooltip
                            location="right"
                          >
                            <template #activator="{ props }">
                              <VChip
                                v-bind="props"
                                class="ms-1 p-1 font-weight-bold"
                                color="warning"
                                text-color="white"
                                small
                                append-icon="tabler-coins"
                              >
                                $ {{ team.insurance_deposit }}
                              </VChip>
                            </template>
                            <span>
                              {{ team.team_name }} {{ $t ('insurance_deposit') }}
                            </span>
                          </VTooltip>
                        </VTab>
                      </VTabs>

                      <VCardText>
                        <VWindow v-model="tab_settings.team_tab">
                          <VWindowItem
                            v-for="team in item.data"
                            :key="team.team_name"
                          >
                            <VList>
                              <VListItem
                                v-for="person in team.data"
                                :key="person.username"
                              >
                                <template #prepend>
                                  <VIcon
                                    icon="tabler-user"
                                    class="me-3"
                                  />
                                </template>

                                <VListItemTitle>
                                  <span class="font-weight-bold">@{{ person.username }}</span>
                                  <VTooltip
                                    location="right"
                                  >
                                    <template #activator="{ props }">
                                      <VChip
                                        v-bind="props"
                                        class="ms-1 p-1"
                                        color="success"
                                        text-color="white"
                                        small
                                      >
                                        $ {{ person.available_balance_amount }}
                                      </VChip>
                                    </template>
                                    <span>
                                      {{ $t ('available_balance') }}
                                    </span>
                                  </VTooltip>
                                  <VTooltip
                                    location="right"
                                  >
                                    <template #activator="{ props }">
                                      <VChip
                                        v-bind="props"
                                        class="ms-1 p-1"
                                        color="info"
                                        text-color="white"
                                        small
                                        append-icon="tabler-snowflake"
                                      >
                                        $ {{ person.frozen_balance_amount }}
                                      </VChip>
                                    </template>
                                    <span>
                                      {{ $t ('frozen_balance') }}
                                    </span>
                                  </VTooltip>
                                </VListItemTitle>
                              </VListItem>
                            </VList>
                          </VWindowItem>
                        </VWindow>
                      </VCardText>
                    </VWindowItem>
                  </VWindow>
                </VCardText>
              </VCard>
            </VCard>
          </VCol>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
