<script setup>
import { avatarText, resolveRole } from '@core/utils/formatters'
import { useAuthStore } from "@/stores/useAuthStore"

const props = defineProps ({
  userData: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits ([ 'update:userData' ])

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const authStore = useAuthStore ()

const windowUrl = computed (
  () => {
    return window.location.origin
  },
)

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

const getUser = () => {
  emit ('update:userData', null)
  authStore.me ({}).then (
    () => {
      // console.log (authStore.userData)
      emit ('update:userData', authStore.userData)
    },
  )
}
</script>

<template>
  <VRow>
    <VSnackbar
      v-model="snackbar.enabled"
      location="bottom end"
      variant="flat"
      transition="scroll-y-reverse-transition"
      :color="snackbar.type"
    >
      {{ snackbar.message }}
    </VSnackbar>

    <VCol cols="12">
      <VCard v-if="props.userData">
        <VCardText class="text-center pt-15">
          <VRow class="mt-n10">
            <VSpacer />
            <VBtn
              icon="tabler-refresh"
              size="small"
              variant="plain"
              @click="getUser"
            />
          </VRow>
          <VAvatar
            rounded
            :size="120"
            color="primary"
            variant="tonal"
          >
            <span
              class="text-5xl font-weight-semibold"
            >
              {{ avatarText (props.userData.email) }}
            </span>
          </VAvatar>
          <h6 class="text-h6 mt-4">
            {{ props.userData.email }}
          </h6>
          <VChip
            v-bind="resolveRole(props.userData.role).chip"
            class="mt-4"
            size="small"
          >
            {{ resolveRole (props.userData.role).status }}
          </VChip>
        </VCardText>
      </VCard>
    </VCol>
  </VRow>
</template>

<style lang="scss" scoped>
.card-list {
  --v-card-list-gap: 0.7rem;
}

.text-capitalize {
  text-transform: capitalize !important;
}
</style>
