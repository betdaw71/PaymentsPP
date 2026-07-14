<!-- eslint-disable vue/no-mutating-props -->
<script setup>
// import PreSettleDialog from "@/views/user/support/solutions/PreSettleDialog.vue"
// import DepositDialog from "@/views/user/support/solutions/DepositDialog.vue"
// import ChargebackDialog from "@/views/user/support/solutions/ChargebackDialog.vue"

import { useAuthStore } from "@/stores/useAuthStore"

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

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const authStore = useAuthStore ()
const isDepositDialogVisible = ref (false)
const isWithdrawDialogVisible = ref (false)
const isChargebackDialogVisible = ref (false)

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
            <VTextField
              v-if="field_type?.type !== 'bool'"
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
