<!-- eslint-disable vue/no-mutating-props -->
<script setup>
// import PreSettleDialog from "@/views/user/support/solutions/PreSettleDialog.vue"
// import DepositDialog from "@/views/user/support/solutions/DepositDialog.vue"
// import ChargebackDialog from "@/views/user/support/solutions/ChargebackDialog.vue"

import { useAuthStore } from "@/stores/useAuthStore"
import { useBaseStore } from "@/stores/useBaseStore"

const props = defineProps ({
  id: {
    type: Number,
    required: true,
  },
  data: {
    type: Object,
    required: true,
    default: () => ({}),
  },
  workType: {
    type: String,
    required: true,
    default: "by_card",
  },
  fields: {
    type: Object,
    required: true,
    default: () => ({}),
  },
  type: {
    type: String,
    required: true,
  },
})

const emit = defineEmits ([
  'remove',
  'update',
  'save',
])

const { t } = useI18n ()

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const authStore = useAuthStore ()
const baseStore = useBaseStore ()
const isDepositDialogVisible = ref (false)
const isWithdrawDialogVisible = ref (false)
const isChargebackDialogVisible = ref (false)
const qrUploading = ref (false)
const qrFileModel = ref (null)

const localDetail = ref (structuredClone (toRaw (props.data)))
const localFields = ref (structuredClone (toRaw (props.fields)))

watch (localDetail, () => {
  emit ('update', props.id, localDetail.value)
}, { deep: true })

const removeSolution = () => {
  console.log('Removing solution', props.id)
  emit ('remove', props.id)
}

const saveSolution = () => {
  console.log ('Saving solution', localDetail.value)
  emit ('save', props.id, localDetail.value)
}

const clearQrImage = field => {
  localDetail.value[field] = ""
  qrFileModel.value = null
}

const onQrImageSelected = async (field, files) => {
  const file = Array.isArray (files) ? files[0] : files
  if (!file || localDetail.value.id) {
    return
  }
  qrUploading.value = true
  try {
    const response = await baseStore.uploadPaymentDetailsQrImage (file)
    if (response.error) {
      throw response.error
    }
    localDetail.value[field] = response.data?.qr_payload || response.data?.url || ""
    snackbar.value = {
      enabled: true,
      type: "success",
      message: `${t (`fields.${field}`)} ✓`,
    }
  } catch (error) {
    console.error ("QR upload failed", error)
    snackbar.value = {
      enabled: true,
      type: "error",
      message: typeof error === "string" ? error : (error?.file?.[0] || error?.detail || "Upload failed"),
    }
    qrFileModel.value = null
  } finally {
    qrUploading.value = false
  }
}


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
</script>

<template>
  <VCard
    flat
    border
    class="d-flex flex-row"
  >
    <VSnackbar
      v-model="snackbar.enabled"
      :color="snackbar.type"
      :timeout="3000"
      top
    >
      {{ snackbar.message }}
    </VSnackbar>
    <!-- 👉 Left Form -->
    <VCard
      border="0"
      class="pa-5 flex-grow-1"
    >
      <VRow class="pa-1">
        <VCol
          v-if="localDetail.id"
          cols="12"
        >
          <VTextField
            v-model="localDetail.id"
            label="ID"
            readonly
            append-inner-icon="tabler-clipboard"
            @click:append-inner="copyToClipboard(localDetail.id, $t('copied_to_clipboard', {value: $t('fields.id')}), 'success')"
          />
        </VCol>
        <VCol
          v-for="(field_type, field) in localFields"
          :key="field"
          cols="12"
        >
          <template
            v-if="((field_type?.unique && props.id === 0 && props.workType === 'by_card') || !field_type?.unique) && ((props?.workType === 'by_cash' && field_type?.cash) || props?.workType !== 'by_cash')"
          >
            <div v-if="field_type?.type === 'image'">
              <VFileInput
                v-if="!localDetail.id"
                v-model="qrFileModel"
                accept="image/*"
                :label="$t(`fields.${field}`)"
                :loading="qrUploading"
                :disabled="qrUploading"
                prepend-icon="tabler-photo"
                show-size
                @update:model-value="onQrImageSelected(field, $event)"
              />
              <div
                v-if="localDetail[field]"
                class="mt-2"
              >
                <VImg
                  :src="localDetail[field]"
                  max-width="220"
                  max-height="220"
                  class="rounded border"
                />
                <div
                  v-if="!localDetail.id"
                  class="d-flex gap-2 mt-2"
                >
                  <VBtn
                    size="small"
                    variant="tonal"
                    color="error"
                    @click="clearQrImage(field)"
                  >
                    Удалить фото
                  </VBtn>
                </div>
              </div>
              <VAlert
                v-else-if="!localDetail.id"
                class="mt-2"
                type="info"
                variant="tonal"
                density="compact"
              >
                {{ $t(`fields.${field}`) }}: jpg / png
              </VAlert>
            </div>
            <AppSelect
              v-else-if="field_type?.type === 'select'"
              v-model="localDetail[field]"
              :items="field_type.options || []"
              :label="$t(`fields.${field}`)"
              :disabled="!!localDetail.id"
              clearable
            />
            <VTextarea
              v-else-if="field_type?.type === 'textarea'"
              v-model="localDetail[field]"
              :readonly="localDetail.id"
              :label="$t(`fields.${field}`)"
              rows="4"
              auto-grow
            />
            <VTextField
              v-else-if="field_type?.type !== 'bool'"
              v-model="localDetail[field]"
              :type="field_type?.type"
              :readonly="localDetail.id"
              :label="$t(`fields.${field}`)"
              append-inner-icon="tabler-clipboard"
              @click:append-inner="copyToClipboard(localDetail[field], $t('copied_to_clipboard', {value: $t(`fields.${field}`)}), 'success')"
            />
            <VSwitch
              v-else
              v-model="localDetail[field]"
              :false-value="false"
              :readonly="localDetail.id"
              :label="$t(`fields.${field}`)"
            />
          </template>
        </VCol>
      </VRow>
    </VCard>

    <div
      v-if="authStore.is_trader()"
      class="d-flex flex-column justify-space-between border-s pa-1"
    >
      <div>
        <IconBtn @click="removeSolution">
          <VIcon
            size="20"
            icon="tabler-x"
          />
        </IconBtn>
        <IconBtn
          v-if="props.type !== 'creation' && !localDetail.id"
          @click="saveSolution"
        >
          <VIcon
            size="20"
            icon="tabler-device-floppy"
          />
        </IconBtn>
      </div>
    </div>
    <!--    <PreSettleDialog -->
    <!--      v-model:is-dialog-visible="isWithdrawDialogVisible" -->
    <!--      v-model:balance="localDetail.id" -->
    <!--    /> -->
    <!--    <DepositDialog -->
    <!--      v-model:is-dialog-visible="isDepositDialogVisible" -->
    <!--      v-model:balance="localDetail.id" -->
    <!--    /> -->
    <!--    <ChargebackDialog -->
    <!--      v-model:is-dialog-visible="isChargebackDialogVisible" -->
    <!--      v-model:balance="localDetail.id" -->
    <!--    /> -->
  </VCard>
</template>
