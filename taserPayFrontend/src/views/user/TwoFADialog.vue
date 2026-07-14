<script setup>
import { useTradeStore } from "@/stores/useTradeStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { requiredValidator } from "@validators"

const props = defineProps ({
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

const authData = ref ({
  qr_code: null,
})

const setupTwoFA = async () => {
  const result = await refForm.value.validate ()
  if (!result?.valid) {
    console.log ("validation error")

    return
  }
  isLoading.value = true
  authStore.setupTwoFA ({}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: '2FA setup successfully!',
      }
      authData.value = response.data
      isLoading.value = false
      emit ('update:modelValue', false)
      setTimeout (() => {
        emit ('submit', true)
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
  await setupTwoFA ()
}

const onFormReset = () => {
  authData.value = {
    qr_code: null,
  }
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
        <VCardTitle class="text-h5 mb-3">
          {{ t ('user.2fa_dialog.title') }}
        </VCardTitle>
        <p class="mb-0">
          {{ t ('user.2fa_dialog.description') }}
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
            <VAlert
              variant="tonal"
              color="success"
              class="mb-4"
            >
              <VAlertTitle class="mb-1 font-weight-bold">
                {{ $t ('alerts.2fa.requirements') }}
              </VAlertTitle>
              <span>{{ $t ('alerts.2fa.requirements_description') }}</span>
            </VAlert>
          </VRow>
          <VRow
            v-if="authData.qr_code"
          >
            <VCol
              cols="12"
              sm="6"
            >
              <VImg
                :src="'data:image/png;base64,' + authData.qr_code"
                alt="QR Code"
              />
            </VCol>
          </VRow>
          <VRow>
            <VCol
              cols="12"
              class="d-flex flex-wrap justify-center gap-4"
            >
              <VBtn
                :prepend-icon="authData.qr_code ? 'tabler-alert-triangle': 'tabler-x'"
                :color="authData.qr_code ? 'error': 'secondary'"
                variant="tonal"
                @click="onFormReset"
              >
                {{ t ('user.2fa_dialog.reset_btn') }}
              </VBtn>
              <VBtn
                v-if="!authData.qr_code"
                :loading="isLoading"
                prepend-icon="tabler-lock"
                type="submit"
                variant="tonal"
              >
                {{ t ('user.2fa_dialog.submit_btn') }}
              </VBtn>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>
    </VCard>
  </VDialog>
</template>
