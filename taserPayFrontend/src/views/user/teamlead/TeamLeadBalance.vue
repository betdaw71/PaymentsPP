<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import UserWithdrawDialog from "@/views/user/UserWithdrawDialog.vue"
import UserTransferDialog from "@/views/user/UserTransferDialog.vue"

const baseStore = useBaseStore ()
const authStore = useAuthStore ()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const balanceData = ref ({
  "id": "undefined",
  "amount": 0,
  "deposit_address": "0x0000000000000000000000000000000000000000",
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

const updateBalance = () => {
  baseStore.getBalanceTeamLead ({}).then (
    response => {
      if (response.error) {
        snackbar.value = {
          enabled: true,
          type: 'error',
          message: response.error,
        }

        return
      }
      balanceData.value = response.data
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error,
      }
    })
}

onMounted (() => {
  updateBalance ()
})

const isWithdrawDialogOpen = ref (false)
const isTransferDialogOpen = ref (false)
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
              icon="tabler-wallet"
            />
            {{ $t ('user.balance.title') }}
            <VBtn
              class="float-end"
              icon="tabler-refresh"
              size="small"
              @click="updateBalance"
            />
          </VCardTitle>
          <VCol cols="12">
            <VCard :title="$t('wallet')">
              <VCardText>
                <VForm @submit.prevent="() => {}">
                  <VRow class="pt-1">
                    <VCol
                      cols="12"
                    >
                      <VTextField
                        v-model="balanceData.deposit_address"
                        :label="$t('user.balance.deposit_address')"
                        prepend-inner-icon="tabler-link"
                        append-inner-icon="tabler-copy"
                        outlined
                        dense
                        readonly
                        @click:append-inner="copyToClipboard (balanceData.deposit_address, 'Deposit address copied!', 'success')"
                      />
                    </VCol>
                    <VCol
                      cols="4"
                    >
                      <VTextField
                        v-model="balanceData.amount"
                        :label="$t('user.balance.available')"
                        prepend-inner-icon="tabler-pig-money"
                        outlined
                        dense
                        readonly
                      />
                    </VCol>
                    <VCol
                      cols="4"
                    >
                      <VTextField
                        v-model="balanceData.frozen_amount"
                        :label="$t('user.balance.frozen')"
                        append-inner-icon="tabler-snowflake"
                        outlined
                        dense
                        readonly
                      />
                    </VCol>
                    <VCol
                      v-if="authStore.is_merchant()"
                      cols="4"
                    >
                      <VBtn
                        color="primary"
                        type="submit"
                        @click="isWithdrawDialogOpen = true"
                      >
                        {{ $t('withdraw') }}
                      </VBtn>
                    </VCol>
                  </VRow>
                </VForm>
              </VCardText>
            </VCard>
          </VCol>
        </VCard>
      </VCol>
    </VRow>
  </div>
  <UserWithdrawDialog
    v-model:is-dialog-visible="isWithdrawDialogOpen"
    :user-data="authStore.userData"
    :max-amount="balanceData.amount"
  />
  <UserTransferDialog
    v-model:is-dialog-visible="isTransferDialogOpen"
    :max-amount="balanceData.amount"
  />
</template>
