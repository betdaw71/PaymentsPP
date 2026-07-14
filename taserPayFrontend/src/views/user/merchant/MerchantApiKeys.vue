<script setup>
import { useBaseStore } from '@/stores/useBaseStore'
import { useAuthStore } from '@/stores/useAuthStore'
import { usePaymentStore } from "@/stores/usePaymentStore"

const baseStore = useBaseStore ()
const authStore = useAuthStore ()
const paymentStore = usePaymentStore ()

const items = ref ([])

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const generateItem = () => {
  paymentStore.generateKey ({}).then (
    response => {
      if (response.error)
        throw response.error
      console.log ({ response })
      items.value = [ response.data ]
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: "Successfully generated!",
      }
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error,
      }
    },
  )
}

const getItem = async () => {
  paymentStore.getKey ({}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      items.value = structuredClone (toRaw (response.data))
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error,
      }
    },
  )
}

onMounted (
  () => {
    getItem ()
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

const saveWhitelistSettings = () => {
  paymentStore.updateKeyWhitelistById ({
    whitelist_on: items.value[0].whitelist_on,
    whitelist: items.value[0].whitelist_ips,
  }, items.value[0].id).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: "Successfully updated!",
      }
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error,
      }
    },
  )
}
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
              icon="tabler-info-circle"
            />
            {{ $t ('tabs.merchants_api') }}
          </VCardTitle>
          <VCol cols="12">
            <VCard :title="$t('api_keys')">
              <VCardText>
                <VAlert
                  variant="tonal"
                  color="warning"
                  class="mb-4"
                >
                  <VAlertTitle class="mb-1">
                    {{ $t ('alerts.api_key.requirements_description') }}
                  </VAlertTitle>
                  <span>{{ $t ('alerts.api_key.requirements') }}</span>
                </VAlert>

                <VForm @submit.prevent="() => {}">
                  <VRow v-if="items?.length">
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="items[0].token"
                        :label="$t ('token')"
                        readonly
                        append-inner-icon="tabler-clipboard"
                        @click:append-inner="copyToClipboard(items[0].token, `Token copied to clipboard!`, 'success')"
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="items[0].private_key"
                        :label="$t ('private_key')"
                        readonly
                        append-inner-icon="tabler-clipboard"
                        @click:append-inner="copyToClipboard(items[0].private_key, `Private Key copied to clipboard!`, 'success')"
                      />
                    </VCol>
                  </VRow>
                  <VRow>
                    <VCol
                      v-if="items?.length"
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        :model-value="(new Date (parseInt (items[0].created_at * 1000)).toUTCString ())"
                        :label="$t ('date')"
                        readonly
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VBtn
                        color="primary"
                        type="submit"
                        @click="generateItem"
                      >
                        {{ items?.length ? $t('update') : $t('generate') }} {{ $t('api_key') }}
                      </VBtn>
                    </VCol>
                  </VRow>
                </VForm>
              </VCardText>
            </VCard>
          </VCol>
          <VCol
            v-if="items?.length"
            cols="12"
          >
            <VCard :title="$t('whitelist')">
              <VCardText>
                <VForm @submit.prevent="() => {}">
                  <VRow v-if="items?.length">
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VSwitch
                        v-model="items[0].whitelist_on"
                        :label="$t ('whitelist_on')"
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VBtn
                        color="primary"
                        type="submit"
                        @click="saveWhitelistSettings"
                      >
                        {{ $t('save_whitelist_settings') }}
                      </VBtn>
                    </VCol>
                  </VRow>
                  <VRow>
                    <VCol
                      v-for="(item, index) in items[0].whitelist_ips"
                      :key="index"
                      cols="12"
                      md="6"
                    >
                      <VTextField
                        v-model="items[0].whitelist_ips[index]"
                        :label="$t ('whitelist')"
                        outlined
                        append-icon="tabler-trash"
                        @click:append="() => items[0].whitelist_ips.splice (index, 1)"
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VBtn
                        type="submit"
                        variant="tonal"
                        prepend-icon="tabler-plus"
                        @click="() => items[0].whitelist_ips.push ('')"
                      >
                        {{ $t('add_whitelist') }}
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
</template>
