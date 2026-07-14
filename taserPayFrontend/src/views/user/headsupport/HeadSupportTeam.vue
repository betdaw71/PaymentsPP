<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import EditTraderDialog from "@/views/user/EditTraderDialog.vue"
import EditRatesDialog from "@/views/user/headsupport/manage/EditRatesDialog.vue"

const baseStore = useBaseStore ()
const tab_settings = ref (structuredClone (toRaw (baseStore.team_settings)))
const isEditTraderDialogVisible = ref (false)
const isEditDialogVisible = ref (false)
const editData = ref ({})

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const teamData = ref ({
  "team_id": "undefined",
  "traders": [],
  "senior_traders": [],
})

const userData = ref ({
  id: "",
  username: "",
  phone: "",
  email: "",
})

const updateTeam = () => {
  baseStore.getTradingTeamSupport ({}).then (
    response => {
      if (response.error) {
        snackbar.value = {
          enabled: true,
          type: 'error',
          message: response.error,
        }

        return
      }
      teamData.value = response.data.data
      if (teamData.value.length > 0 && !tab_settings.value.tab) {
        tab_settings.value.tab = 0
      }
      console.log ({ teamData: teamData.value })
    },
  ).catch (
    error => {
      console.log ({ error })
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error,
      }
    },
  )
}



const unblockTrader = async user_id => {
  await baseStore.unblockTraderPaymentDetailsCreationById ({}, user_id)
  console.log (`unblockTrader ${user_id}`)
  updateTeam ()
}

const blockTrader = async user_id => {
  await baseStore.blockTraderPaymentDetailsCreationById ({}, user_id)
  console.log (`blockTrader ${user_id}`)
  updateTeam ()
}

const openEditTraderDialog = user => {
  userData.value = user
  isEditTraderDialogVisible.value = true
}


onMounted (
  () => {
    updateTeam ()
  },
)
watch (
  () => tab_settings.value,
  () => {
    baseStore.team_settings = structuredClone (toRaw (tab_settings.value))
  },
  { deep: true },
)

const editRates = team => {
  isEditDialogVisible.value = true

  const teamEditData = structuredClone (toRaw (team))
  if (!teamEditData.fees) {
    teamEditData.fees = []
  }
  editData.value = teamEditData
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
              icon="tabler-vector-triangle"
            />
            {{ $t ('tabs.team') }}
            <VBtn
              class="float-end"
              icon="tabler-refresh"
              size="small"
              @click="updateTeam"
            />
          </VCardTitle>
          <VTabs
            v-model="tab_settings.tab"
            show-arrows
          >
            <VTab
              v-for="item in teamData"
              :key="item.team_id"
            >
              {{ item.team_name }}
            </VTab>
          </VTabs>
          <VCardText>
            <VWindow v-model="tab_settings.tab">
              <VWindowItem
                v-for="team in teamData"
                :key="team.team_id"
              >
                <VCol cols="12">
                  <VCard :title="$t('rates')">
                    <VCardText>
                      <VCol
                        cols="12"
                        class="d-flex justify-content-between"
                      >
                        <VCol>
                          <VBtn
                            color="primary"
                            @click="editRates(team)"
                          >
                            {{ $t ('manage_rates') }}
                          </VBtn>
                        </VCol>
                      </vcol>
                    </VCardText>
                  </VCard>
                </VCol>
                <VCol cols="12">
                  <VCard :title="$t('senior_traders')">
                    <VCardText>
                      <VList
                        nav
                        :lines="false"
                      >
                        <VListItem
                          v-for="item in team.senior_trader"
                          :key="item.id"
                        >
                          <template #prepend>
                            <VIcon
                              icon="tabler-user-bolt"
                              class="me-3"
                            />
                          </template>

                          <VListItemTitle
                            class="cursor-pointer"
                            @click="openEditTraderDialog(item)"
                          >
                            <span class="font-weight-bold">@{{ item.username }}</span> ({{ item.email }})

                            <template
                              v-if="item.blocked"
                            >
                              <VTooltip
                                location="end"
                              >
                                <template #activator="{ props }">
                                  <VBtn
                                    v-bind="props"
                                    size="small"
                                    class="ms-2"
                                    color="success"
                                    icon="tabler-lock-access-off"
                                    @click.stop="unblockTrader(item.id)"
                                  />
                                </template>
                                <span>
                                  {{ $t ('unblock') }}
                                </span>
                              </VTooltip>
                            </template>
                            <template
                              v-else
                            >
                              <VTooltip
                                location="end"
                              >
                                <template #activator="{ props }">
                                  <VBtn
                                    v-bind="props"
                                    size="small"
                                    class="ms-2"
                                    color="error"
                                    icon="tabler-lock-access"
                                    @click.stop="blockTrader(item.id)"
                                  />
                                </template>
                                <span>
                                  {{ $t ('block') }}
                                </span>
                              </VTooltip>
                            </template>
                          </VListItemTitle>
                        </VListItem>
                      </VList>
                    </VCardText>
                  </VCard>
                </VCol>
                <VCol cols="12">
                  <VCard :title="$t('traders')">
                    <VCardText>
                      <VList
                        nav
                        :lines="false"
                      >
                        <VListItem
                          v-for="item in team.traders"
                          :key="item.id"
                        >
                          <template #prepend>
                            <VIcon
                              icon="tabler-user"
                              class="me-3"
                            />
                          </template>

                          <VListItemTitle
                            class="cursor-pointer"
                            @click="openEditTraderDialog(item)"
                          >
                            <span class="font-weight-bold">@{{ item.username }}</span> ({{ item.email }})
                            <template
                              v-if="item.blocked"
                            >
                              <VTooltip
                                location="end"
                              >
                                <template #activator="{ props }">
                                  <VBtn
                                    v-bind="props"
                                    size="small"
                                    class="ms-2"
                                    color="success"
                                    icon="tabler-lock-access-off"
                                    @click.stop="unblockTrader(item.id)"
                                  />
                                </template>
                                <span>
                                  {{ $t ('unblock') }}
                                </span>
                              </VTooltip>
                            </template>
                            <template
                              v-else
                            >
                              <VTooltip
                                location="end"
                              >
                                <template #activator="{ props }">
                                  <VBtn
                                    v-bind="props"
                                    size="small"
                                    class="ms-2"
                                    color="error"
                                    icon="tabler-lock-access"
                                    @click.stop="blockTrader(item.id)"
                                  />
                                </template>
                                <span>
                                  {{ $t ('block') }}
                                </span>
                              </VTooltip>
                            </template>
                          </VListItemTitle>
                        </VListItem>
                      </VList>
                    </VCardText>
                  </VCard>
                </VCol>
              </VWindowItem>
            </VWindow>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
    <EditTraderDialog
      v-model:is-dialog-visible="isEditTraderDialogVisible"
      :user-data="userData"
    />
    <EditRatesDialog
      v-model:is-dialog-visible="isEditDialogVisible"
      :data="editData"
      @update="updateTeam"
    />
  </div>
</template>
