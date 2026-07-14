<script setup>
import { useTradeStore } from "@/stores/useTradeStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { requiredValidator } from "@validators"

const props = defineProps ({
  withdrawalData: {
    type: Object,
    required: false,
    default: () => {
      return {
        address: "",
        comment: "",
        amount: 0,
        status: "creation",
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

const refForm = ref ()
const isLoading = ref (false)
const { t } = useI18n ()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const tradeStore = useTradeStore ()
const authStore = useAuthStore ()
const withdrawalData = ref (structuredClone (toRaw (props.withdrawalData)))

watch (props, () => {
  withdrawalData.value = structuredClone (toRaw (props.withdrawalData))
})

const createWithdrawal = async () => {
  const result = await refForm.value.validate ()
  if (!result?.valid) {
    console.log ("validation error")

    return
  }
  isLoading.value = true
  tradeStore.createTradeWithdrawalRequest ({
    address: withdrawalData.value.address,
    comment: withdrawalData.value.comment,
    amount: withdrawalData.value.amount,
  }).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: 'Withdrawal request created successfully!',
      }
      isLoading.value = false
      emit ('update:modelValue', false)
      setTimeout (() => {
        emit ('update:modelValue', false)
        emit ('update:isDialogVisible', false)
        emit('submit', true)
      }, 2000)
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error,
      }
      isLoading.value = false
    },
  )

}

const onFormSubmit = async () => {
  await createWithdrawal ()
}

const onFormReset = () => {
  withdrawalData.value = structuredClone (toRaw (props.withdrawalData))
  emit ('update:isDialogVisible', false)
}

const dialogModelValueUpdate = val => {
  emit ('update:isDialogVisible', val)
}

watch (
  () => withdrawalData.value,
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
    <!-- Dialog close btn -->
    <DialogCloseBtn @click="dialogModelValueUpdate(false)" />

    <VCard class="pa-sm-14 pa-5">
      <VCardItem class="text-center">
        <VCardTitle class="text-h5 mb-3">
          {{ t ('user.withdrawal_dialog.title') }}
        </VCardTitle>
        <p class="mb-0">
          {{ t ('user.withdrawal_dialog.description') }}
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
              sm="9"
            >
              <VTextField
                v-model="withdrawalData.address"
                prepend-inner-icon="tabler-link"
                :label="$t('address')"
                :rules="[
                  requiredValidator,
                ]"
              />
            </VCol>
            <VCol
              cols="12"
              sm="3"
            >
              <VTextField
                v-model="withdrawalData.amount"
                type="number"
                prepend-inner-icon="tabler-coin"
                :label="$t('usd_amount')"
                :rules="[
                  requiredValidator,
                  v => props.maxAmount ? v <= props.maxAmount || 'Amount must be less than or equal to ' + props.maxAmount: true,
                ]"
              />
            </VCol>
            <VCol
              cols="12"
              class="d-flex flex-wrap justify-center gap-4"
            >
              <VBtn
                v-if="withdrawalData.status === 'creation'"
                :loading="isLoading"
                type="submit"
              >
                {{ t ('user.withdrawal_dialog.submit_btn') }}
              </VBtn>

              <VBtn
                color="secondary"
                variant="tonal"
                @click="onFormReset"
              >
                {{ t ('user.withdrawal_dialog.reset_btn') }}
              </VBtn>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>
    </VCard>
  </VDialog>
</template>
