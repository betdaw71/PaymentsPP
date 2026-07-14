<script setup>
import { useTradeStore } from "@/stores/useTradeStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { useBaseStore } from "@/stores/useBaseStore"
import { differentValidator, requiredValidator, uniqueValidator } from "@validators"

const props = defineProps ({
  transferData: {
    type: Object,
    required: false,
    default: () => {
      return {
        to_balance: "",
        from_balance: "",
        amount: 0,
      }
    },
  },
  maxAmount: {
    type: Number,
    required: false,
    default: 0,
  },
  isDialogVisible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits ([
  'update:modelValue',
  'submit',
  'update:isDialogVisible',
])

const isLoading = ref (false)
const from_balances = ref ([])
const to_balances = ref ([])

const { t } = useI18n ()
const refForm = ref (null)

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const tradeStore = useTradeStore ()
const baseStore = useBaseStore ()
const authStore = useAuthStore ()
const transferData = ref (structuredClone (toRaw (props.transferData)))

watch (props, () => {
  transferData.value = structuredClone (toRaw (props.transferData))
})

const createTransfer = async () => {
  const result = await refForm.value.validate ()
  if (!result?.valid) {
    console.log ("validation error")

    return
  }
  isLoading.value = true
  baseStore.transferBalance ({
    to_balance: transferData.value.to_balance,
    from_balance: transferData.value.from_balance,
    amount: transferData.value.amount,
  }).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: 'Transfer created successfully!',
      }
      isLoading.value = false
      setTimeout (() => {
        emit ('update:modelValue', false)
        emit ('update:isDialogVisible', false)
        emit('submit', true)
      }, 2000)
    },
  ).catch (error => {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: error,
    }
    isLoading.value = false
  })

}

const onFormSubmit = async () => {
  await createTransfer ()
}

const onFormReset = () => {
  transferData.value = structuredClone (toRaw (props.transferData))
  emit ('update:isDialogVisible', false)
}

const dialogModelValueUpdate = val => {
  emit ('update:isDialogVisible', val)
}

const getAddresses = async () => {
  await baseStore.getTransferTargets ({}).then (
    response => {
      if (response.error) {
        snackbar.value = {
          enabled: true,
          type: 'error',
          message: response.error,
        }

        return
      }
      from_balances.value = response.data.from
      to_balances.value = response.data.to
      if (from_balances.value.length > 0 && !transferData.value.from_balance) {
        transferData.value.from_balance = from_balances.value[0].balance_id
      }
      if (to_balances.value.length > 0 && !transferData.value.to_balance) {
        transferData.value.to_balance = to_balances.value[0].balance_id
      }
    },
  ).catch (error => {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: error,
    }
  })
}

const maxAmount = computed (() => {
  return transferData.value.from_balance ? from_balances.value.find (balance => balance.balance_id === transferData.value.from_balance).amount : 0
})

watch (
  () => props.isDialogVisible,
  () => {
    if (props.isDialogVisible) {
      getAddresses ()
    }
  },
)
watch (
  () => transferData.value,
  () => {
    nextTick (() => {
      refForm.value?.resetValidation ()
      refForm.value?.validate ()
    })
  },
  { deep: true },
)
</script>

<template>
  <VDialog
    :width="$vuetify.display.smAndDown ? 'auto' : 700"
    :model-value="props.isDialogVisible"
    @update:model-value="dialogModelValueUpdate"
  >
    <VSnackbar
      v-model="snackbar.enabled"
      :color="snackbar.type"
      :timeout="3000"
      top
    >
      {{ snackbar.message }}
    </VSnackbar>
    <DialogCloseBtn @click="dialogModelValueUpdate(false)" />

    <VCard class="pa-sm-14 pa-5">
      <VCardItem class="text-center">
        <VCardTitle class="text-h5 mb-3">
          {{ t ('user.transfer_dialog.title') }}
        </VCardTitle>
        <p class="mb-0">
          {{ t ('user.transfer_dialog.description') }}
        </p>
      </VCardItem>

      <VCardText>
        <!-- 👉 Form -->
        <VForm
          ref="refForm"
          class="mt-6"
          @submit.prevent="onFormSubmit"
        >
          <VRow>
            <VCol
              cols="12"
            >
              <VSelect
                v-model="transferData.from_balance"
                :loading="from_balances.length === 0"
                :items="from_balances"
                item-title="username"
                item-value="balance_id"
                prepend-inner-icon="tabler-link"
                density="compact"
                :label="$t('from')"
                :rules="[
                  requiredValidator,
                  differentValidator(transferData.from_balance, transferData.to_balance, t('from'), t('to')),
                ]"
              />
            </VCol>
            <VCol
              cols="12"
            >
              <VSelect
                v-model="transferData.to_balance"
                :loading="to_balances.length === 0"
                :items="to_balances"
                item-title="username"
                item-value="balance_id"
                prepend-inner-icon="tabler-link"
                :label="$t('to')"
                :rules="[
                  requiredValidator,
                  differentValidator(transferData.from_balance, transferData.to_balance, t('from'), t('to')),
                ]"
              />
            </VCol>
            <VCol
              cols="12"
              md="6"
            >
              <VTextField
                v-model="transferData.amount"
                :label="$t('amount')"
                type="number"
                :rules="[
                  requiredValidator,
                  v => maxAmount ? v <= maxAmount || 'Amount must be less than or equal to ' + maxAmount: true,
                ]"
              />
            </VCol>
            <VCol
              cols="12"
              class="d-flex flex-wrap justify-center gap-4"
            >
              <VBtn
                :loading="isLoading"
                type="submit"
              >
                {{ t ('user.transfer_dialog.submit') }}
              </VBtn>

              <VBtn
                color="secondary"
                variant="tonal"
                @click="onFormReset"
              >
                {{ t ('user.transfer_dialog.reset') }}
              </VBtn>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>
    </VCard>
  </VDialog>
</template>
