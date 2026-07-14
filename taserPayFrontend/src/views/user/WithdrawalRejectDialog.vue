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
        id: "",
        from_user: "",
        amount: 0,
      }
    },
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
const { t } = useI18n ()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const withdrawalForm = ref ({
  comment: "",
})

const tradeStore = useTradeStore ()
const authStore = useAuthStore ()
const withdrawalData = ref (structuredClone (toRaw (props.withdrawalData)))

watch (props, () => {
  withdrawalData.value = structuredClone (toRaw (props.withdrawalData))
})

const rejectWithdrawal = () => {
  tradeStore.rejectTradeWithdrawalRequestById ({
    comment: withdrawalForm.value.comment,
  }, withdrawalData.value.id).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: t ('withdrawals.rejected'),
      }
      setTimeout (() => {
        emit ('update:modelValue', false)
        emit ('update:isDialogVisible', false)
      }, 2000)
    }).catch (error => {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: error,
    }
  })
}

const onFormSubmit = async () => {
  await rejectWithdrawal ()
}

const onFormReset = () => {
  withdrawalData.value = structuredClone (toRaw (props.withdrawalData))
  emit ('update:isDialogVisible', false)
}

const dialogModelValueUpdate = val => {
  emit ('update:isDialogVisible', val)
}
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
        <VCardTitle class="text-h5 mb-3 text-wrap">
          {{ t ('user.withdrawal_reject_dialog.title') }} @{{ withdrawalData.from_user }} (USD {{
            withdrawalData.amount
          }})
        </VCardTitle>
        <p class="mb-0">
          {{ t ('user.withdrawal_reject_dialog.description') }}
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
              <VTextField
                v-model="withdrawalForm.comment"
                prepend-inner-icon="tabler-message-dots"
                :label="t ('user.withdrawal_reject_dialog.comment')"
                :rules="[
                  requiredValidator,
                ]"
              />
            </VCol>
            <VCol
              cols="12"
              class="d-flex flex-wrap justify-center gap-4"
            >
              <VBtn
                type="submit"
              >
                {{ t ('user.withdrawal_reject_dialog.submit_btn') }}
              </VBtn>

              <VBtn
                color="secondary"
                variant="tonal"
                @click="onFormReset"
              >
                {{ t ('user.withdrawal_reject_dialog.reset_btn') }}
              </VBtn>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>
    </VCard>
  </VDialog>
</template>
