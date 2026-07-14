<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import UserTransferDialog from "@/views/user/UserTransferDialog.vue"
import UserWithdrawDialog from "@/views/user/UserWithdrawDialog.vue"

const baseStore = useBaseStore ()
const authStore = useAuthStore ()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const balanceData = ref ({
  "my_balance": {
    "id": "undefined",
    "username": "undefined",
    "available_balance_amount": 0.0,
    "available_balance_id": "undefined",
    "frozen_balance_amount": 0.0,
    "frozen_balance_id": "undefined",
    "insurance_deposit": 0.0,
    "deposit_address": "0x0000000000000000000000000000000000000000",
  },
  "sub_balances": [],
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
  baseStore.getBalanceTrader ({}).then (
    response => {
      if (response.error) {
        throw response.error

      }
      balanceData.value = response.data
      console.log ({ balanceData: balanceData.value })
    },
  ).catch (
    error => {
      console.error ('Failed to get balance: ', error)
      snackbar.value = {
        enabled: true,
        type: "error",
        message: `Error occurred: ${error}`,
      }
    },
  )
}

onMounted (
  () => {
    updateBalance ()
  },
)


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
            {{ $t('tabs.balance') }}
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
                        v-model="balanceData.my_balance.deposit_address"
                        :label="$t('deposit_address')"
                        prepend-inner-icon="tabler-link"
                        append-inner-icon="tabler-copy"
                        outlined
                        dense
                        readonly
                        @click:append-inner="copyToClipboard (balanceData.my_balance.deposit_address, 'Deposit address copied!', 'success')"
                      />
                    </VCol>
                  </VRow>
                  <VRow class="pt-1">
                    <VCol
                      cols="6"
                      sm="3"
                    >
                      <VTextField
                        v-model="balanceData.my_balance.available_balance_amount"
                        :label="$t('available_balance')"
                        prepend-inner-icon="tabler-pig-money"
                        outlined
                        dense
                        readonly
                      />
                    </VCol>
                    <VCol
                      cols="6"
                      sm="3"
                    >
                      <VTextField
                        v-model="balanceData.my_balance.frozen_balance_amount"
                        :label="$t('frozen_balance')"
                        append-inner-icon="tabler-snowflake"
                        outlined
                        dense
                        readonly
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="balanceData.my_balance.insurance_deposit"
                        :label="$t('insurance_deposit')"
                        prepend-inner-icon="tabler-coins"
                        outlined
                        dense
                        readonly
                      />
                    </VCol>
                    <VCol
                      v-if="authStore.is_trader()"
                      cols="6"
                      sm="3"
                    >
                      <VBtn
                        color="warning"
                        type="submit"
                        @click="isTransferDialogOpen = true"
                      >
                        Transfer
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
  <UserTransferDialog
    v-model:is-dialog-visible="isTransferDialogOpen"
    :max-amount="balanceData.my_balance.available_balance_amount"
    @submit="updateBalance"
  />
</template>
