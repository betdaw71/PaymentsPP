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

const teamData = ref ([])

const updateTeam = () => {
  baseStore.getBalanceSupportMerchant ({}).then (
    response => {
      if (response.error) {
        snackbar.value = {
          enabled: true,
          type: 'error',
          message: response.error,
        }

        return
      }
      teamData.value = response.data
      console.log ({ teamData: teamData.value })
    },
  ).catch(
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
              icon="tabler-coin"
            />
            {{ $t('tabs.merchants_balance') }}
            <VBtn
              class="float-end"
              icon="tabler-refresh"
              size="small"
              @click="updateTeam"
            />
          </VCardTitle>
          <VCol cols="12">
            <VCard>
              <VCardText>
                <VList>
                  <VListItem
                    v-for="item in teamData"
                    :key="item.id"
                  >
                    <template #prepend>
                      <VIcon
                        icon="tabler-user"
                        class="me-3"
                      />
                    </template>

                    <VListItemTitle>
                      <span class="font-weight-bold">@{{ item.username }}</span>
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
                            $ {{ item.available_balance_amount }}
                          </VChip>
                        </template>
                        <span>
                          {{ $t('available_balance') }}
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
                            $ {{ item.frozen_balance_amount }}
                          </VChip>
                        </template>
                        <span>
                          {{ $t('frozen_balance') }}
                        </span>
                      </VTooltip>
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
