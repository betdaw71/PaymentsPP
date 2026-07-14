<script setup>
import { useTradeStore } from "@/stores/useTradeStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { requiredValidator } from "@validators"

const props = defineProps ({
  userData: {
    type: Object,
    required: false,
    default: () => {
      return {
        id: "",
        username: "",
        telegram: "",
        phone: "",
        email: "",
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


const tradeStore = useTradeStore ()
const authStore = useAuthStore ()
const userData = ref (structuredClone (toRaw (props.userData)))

watch (props, () => {
  userData.value = structuredClone (toRaw (props.userData))
})

const updateUser = () => {
  authStore.updateUser ({
    username: userData.value.username,
    phone: userData.value.phone,
    telegram: userData.value.telegram,
    email: userData.value.email,
  }, userData.value.id).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: t ('user.user_update.success_message'),
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
  await updateUser ()
}

const onFormReset = () => {
  userData.value = structuredClone (toRaw (props.userData))
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
          {{ t ('user.user_update.title') }} {{ userData.email }}
        </VCardTitle>
        <p class="mb-0">
          {{ t ('user.user_update.description') }}
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
                v-model="userData.username"
                prepend-inner-icon="tabler-at"
                :label="t ('username')"
                :rules="[
                  requiredValidator,
                ]"
              />
            </VCol>
            <VCol
              cols="12"
            >
              <VTextField
                v-model="userData.phone"
                prepend-inner-icon="tabler-phone"
                :label="t ('phone')"
                :rules="[
                  requiredValidator,
                ]"
              />
            </VCol>
            <VCol
              cols="12"
            >
              <VTextField
                v-model="userData.telegram"
                prepend-inner-icon="tabler-brand-telegram"
                :label="t ('telegram')"
                :rules="[
                  requiredValidator,
                ]"
              />
            </VCol>
            <VCol
              cols="12"
            >
              <VTextField
                v-model="userData.email"
                prepend-inner-icon="tabler-mail"
                :label="t ('email')"
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
                {{ t ('user.withdrawal_approve_dialog.submit_btn') }}
              </VBtn>

              <VBtn
                color="secondary"
                variant="tonal"
                @click="onFormReset"
              >
                {{ t ('user.withdrawal_approve_dialog.reset_btn') }}
              </VBtn>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>
    </VCard>
  </VDialog>
</template>
