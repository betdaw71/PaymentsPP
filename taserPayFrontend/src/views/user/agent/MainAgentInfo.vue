<script setup>
import { useAuthStore } from '@/stores/useAuthStore'

const authStore = useAuthStore()
const userData = ref(JSON.parse(JSON.stringify(authStore.userData)))

const isOldPasswordVisible = ref(false)
const isNewPasswordVisible = ref(false)
const isConfirmPasswordVisible = ref(false)

const oldPassword = ref("")
const newPassword = ref("")
const confirmPassword = ref("")

const snackbar = ref({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const updatePassword = () => {
  authStore.changePassword({
    old_password: oldPassword.value,
    password: newPassword.value,
    password2: confirmPassword.value,
  }).then(
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: "Successfully changed password!",
      }
    },
  ).catch(
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
            Main Info
          </VCardTitle>
          <VCol cols="12">
            <VCard :title="$t('base_info')">
              <VCardText>
                <VRow>
                  <VCol cols="6">
                    <VTextField
                      v-model="userData.username"
                      :label="$t('username')"
                      readonly
                    />
                  </VCol>
                  <VCol cols="6">
                    <VTextField
                      v-model="userData.email"
                      :label="$t('email')"
                      readonly
                    />
                  </VCol>
                </VRow>
              </VCardText>
            </VCard>
          </VCol>
          <VCol cols="12">
            <VCard :title="$t('change_password')">
              <VCardText>
                <VForm @submit.prevent="() => {}">
                  <VRow>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="oldPassword"
                        :label="$t('old_password')"
                        :type="isOldPasswordVisible ? 'text' : 'password'"
                        :append-inner-icon="isOldPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                        @click:append-inner="isOldPasswordVisible = !isOldPasswordVisible"
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="newPassword"
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
                        v-model="confirmPassword"
                        :label="$t('confirm_password')"
                        :type="isConfirmPasswordVisible ? 'text' : 'password'"
                        :append-inner-icon="isConfirmPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                        @click:append-inner="isConfirmPasswordVisible = !isConfirmPasswordVisible"
                      />
                    </VCol>
                    <VCol cols="12">
                      <VBtn
                        color="primary"
                        @click="updatePassword"
                      >
                        {{ $t('change_password') }}
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
