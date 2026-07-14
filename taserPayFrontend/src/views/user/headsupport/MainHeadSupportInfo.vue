<script setup>
import { useBaseStore } from '@/stores/useBaseStore'
import { useAuthStore } from '@/stores/useAuthStore'
import TwoFADialog from '@/views/user/TwoFADialog.vue'

const baseStore = useBaseStore ()
const authStore = useAuthStore ()
const userData = ref (JSON.parse (JSON.stringify (authStore.userData)))

const isOldPasswordVisible = ref (false)
const isNewPasswordVisible = ref (false)
const isConfirmPasswordVisible = ref (false)
const isTwoFADialogVisible = ref (false)

const oldPassword = ref ("")
const newPassword = ref ("")
const confirmPassword = ref ("")

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const updatePassword = () => {
  authStore.changePassword ({
    old_password: oldPassword.value,
    password: newPassword.value,
    password2: confirmPassword.value,
  }).then (
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

const updateUserInfo = async () => {
  baseStore.updateSupportMemberById ({
    telegram: userData.value.telegram,
    phone: userData.value.phone,
  }, userData.value.object_id).then(
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
  ).catch(
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error,
      }
    },
  )

  console.log ("updateUserInfo", userData.value)
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
            <!-- 👉 Change password -->
            <VCard :title="$t('base_info')">
              <VCardText>
                <VForm @submit.prevent="() => {}">
                  <VRow class="pt-1">
                    <VCol
                      cols="12"
                      sm="6"
                      md="6"
                    >
                      <VTextField
                        v-model="userData.first_name"
                        :label="$t('name')"
                        outlined
                        dense
                        readonly
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                      md="6"
                    >
                      <VTextField
                        v-model="userData.email"
                        :label="$t('email')"
                        outlined
                        dense
                        readonly
                      />
                    </VCol>
                  </VRow>
                  <VRow class="pt-1">
                    <VCol
                      cols="12"
                      sm="6"
                      md="6"
                    >
                      <VTextField
                        v-model="userData.telegram"
                        :label="$t('telegram')"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                      md="6"
                    >
                      <VTextField
                        v-model="userData.phone"
                        :label="$t('phone')"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VBtn
                        color="primary"
                        type="submit"
                        :disabled="JSON.stringify(authStore.userData) === JSON.stringify(userData)"
                        @click="updateUserInfo"
                      >
                        {{ $t('update_user') }}
                      </VBtn>
                    </VCol>
                  </VRow>
                </VForm>
              </VCardText>
            </VCard>
          </VCol>
          <VCol cols="12">
            <!-- 👉 Change password -->
            <VCard :title="$t('change_password')">
              <VCardText>
                <VAlert
                  variant="tonal"
                  color="warning"
                  class="mb-4"
                >
                  <VAlertTitle class="mb-1">
                    {{ $t('alerts.requirements') }}
                  </VAlertTitle>
                  <span>{{ $t('alerts.password.requirements') }}</span>
                </VAlert>

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
                    <VCol
                      cols="6"
                      sm="4"
                    >
                      <VBtn
                        color="primary"
                        type="submit"
                        @click="updatePassword"
                      >
                        {{ $t('change_password') }}
                      </VBtn>
                    </VCol>
                    <VCol
                      cols="6"
                      sm="2"
                    >
                      <VBtn
                        prepend-icon="tabler-auth-2fa"
                        color="success"
                        variant="tonal"
                        @click="isTwoFADialogVisible = true"
                      >
                        {{ $t('2fa_setup') }}
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
    <TwoFADialog
      v-model:is-dialog-visible="isTwoFADialogVisible"
    />
  </div>
</template>
