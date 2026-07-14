<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { requiredValidator } from "@validators"

const authStore = useAuthStore ()
const baseStore = useBaseStore ()
const isLoading = ref (false)

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const merchantDataBase = {
  username: "",
  password: "",
  password2: "",
  email: "",
  first_name: "",

  // address: null,
}


const merchantData = ref (structuredClone (toRaw (merchantDataBase)))


const teams = ref ([])


const isNewPasswordVisible = ref (false)
const isConfirmPasswordVisible = ref (false)

const createUser = () => {
  isLoading.value = true
  authStore.registerMerchant ({
    ...merchantData.value,
  }).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: 'Merchant created successfully!',
      }
      merchantData.value = structuredClone (toRaw (merchantDataBase))
      isLoading.value = false
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error.message,
      }
      isLoading.value = false
    },
  )
}

onMounted (
  () => {
    merchantData.value = structuredClone (toRaw (merchantDataBase))
  },
)
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
              icon="tabler-user-plus"
            />
            {{ $t ('tabs.add_merchant') }}
          </VCardTitle>
          <VCol cols="12">
            <!-- 👉 Change password -->
            <VCard :title="$t('base_info')">
              <VCardText>
                <VAlert
                  variant="tonal"
                  color="warning"
                  class="mb-4"
                >
                  <VAlertTitle class="mb-1">
                    {{ $t('alerts.password.requirements_description') }}
                  </VAlertTitle>
                  <span>{{ $t('alerts.password.requirements') }}</span>
                </VAlert>
                <VForm @submit.prevent="() => {}">
                  <VRow class="pt-1">
                    <VCol
                      cols="12"
                      sm="4"
                    >
                      <VTextField
                        v-model="merchantData.username"
                        :label="$t('username')"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="4"
                    >
                      <VTextField
                        v-model="merchantData.email"
                        :label="$t('email')"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="4"
                    >
                      <VTextField
                        v-model="merchantData.first_name"
                        :label="$t('name')"
                        outlined
                        dense
                      />
                    </VCol>
                  </VRow>
                  <VRow class="pt-1">
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="merchantData.password"
                        :label="$t('new_password')"
                        :type="isNewPasswordVisible ? 'text' : 'password'"
                        :append-inner-icon="isNewPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                        @click:append-inner="isNewPasswordVisible = !isNewPasswordVisible"
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="merchantData.password2"
                        :label="$t('confirm_password')"
                        :type="isConfirmPasswordVisible ? 'text' : 'password'"
                        :append-inner-icon="isConfirmPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                        @click:append-inner="isConfirmPasswordVisible = !isConfirmPasswordVisible"
                      />
                    </VCol>
                  </VRow>
                  <VRow>
                    <VCol
                      cols="12"
                      sm="4"
                    >
                      <VBtn
                        :loading="isLoading"
                        color="primary"
                        type="submit"
                        @click="createUser"
                      >
                        {{ $t ('create') }}
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

