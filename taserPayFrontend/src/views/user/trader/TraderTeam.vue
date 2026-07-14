<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { formatUUID } from "@core/utils/formatters"

const baseStore = useBaseStore ()
const authStore = useAuthStore ()

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

const updateTeam = () => {
  baseStore.getTradingTeamTrader ({}).then (
    response => {
      if (response.error) {
        snackbar.value = {
          enabled: true,
          type: 'error',
          message: response.error,
        }

        return
      }
      teamData.value = response.data.data[0]
      console.log ({ teamData: teamData.value })
    },
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


onMounted(
  () => {
    updateTeam ()
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
          <VCol cols="12">
            <VCard :title="$t('senior_traders')">
              <VCardText>
                <VList
                  nav
                  :lines="false"
                >
                  <VListItem
                    v-for="item in teamData.senior_trader"
                    :key="item.id"
                  >
                    <template #prepend>
                      <VIcon
                        icon="tabler-user-bolt"
                        class="me-3"
                      />
                    </template>

                    <VListItemTitle>
                      <span class="font-weight-bold">@{{ item.username }}</span> ({{ item.email }})
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
                    v-for="item in teamData.traders"
                    :key="item.id"
                  >
                    <template #prepend>
                      <VIcon
                        icon="tabler-user"
                        class="me-3"
                      />
                    </template>

                    <VListItemTitle>
                      <span class="font-weight-bold">@{{ item.username }}</span> ({{ item.email }})
                    </VListItemTitle>
                  </VListItem>
                </VList>
              </VCardText>
            </VCard>
          </VCol>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>
