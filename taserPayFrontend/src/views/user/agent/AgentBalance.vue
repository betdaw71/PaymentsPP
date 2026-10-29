<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import UserWithdrawDialog from "@/views/user/UserWithdrawDialog.vue"

const baseStore = useBaseStore()
const authStore = useAuthStore()

const snackbar = ref({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const balanceData = ref({
  amount: 0,
  frozen_amount: 0,
  commission_percent: '0',
  merchants: [],
})

const updateBalance = () => {
  baseStore.getBalanceAgent({}).then(
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
  ).catch(
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error,
      }
    },
  )
}

onMounted(() => {
  updateBalance()
})

const isWithdrawDialogOpen = ref(false)
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
            {{ $t('user.balance.title') }}
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
                    <VCol cols="4">
                      <VTextField
                        v-model="balanceData.amount"
                        :label="$t('user.balance.available')"
                        prepend-inner-icon="tabler-pig-money"
                        outlined
                        dense
                        readonly
                      />
                    </VCol>
                    <VCol cols="4">
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
                      v-if="authStore.is_agent()"
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
                    <VCol cols="12">
                      <VChip
                        color="info"
                        class="me-1"
                      >
                        {{ balanceData.commission_percent }}%
                      </VChip>
                      <VChip
                        v-for="name in balanceData.merchants"
                        :key="name"
                        class="me-1"
                        color="secondary"
                      >
                        {{ name }}
                      </VChip>
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
    :max-amount="Number(balanceData.amount)"
  />
</template>
