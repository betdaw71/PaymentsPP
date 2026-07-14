<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { requiredValidator } from "@validators"
import { useMerchantStore } from "@/stores/useMerchantStore"

const authStore = useAuthStore ()
const baseStore = useBaseStore ()
const merchantStore = useMerchantStore ()
const isLoading = ref (false)

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const supportDataBase = {
  username: "",
  password: "",
  password2: "",
  email: "",
  first_name: "",
  controlled_teams: [],
  controlled_merchants: [],
}

const supportData = ref (structuredClone (toRaw (supportDataBase)))

const teams = ref ([])
const merchants = ref ([])

const isNewPasswordVisible = ref (false)
const isConfirmPasswordVisible = ref (false)

const updateTeams = () => {
  baseStore.getTraderTeam ({}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      teams.value = response.data
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error.message,
      }
    },
  )
}

const updateMerchants = () => {
  merchantStore.getMerchant ({}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      merchants.value = response.data
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error.message,
      }
    },
  )
}

const createUser = () => {
  isLoading.value = true
  authStore.registerSupport ({
    ...supportData.value,
  }).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: 'Support created successfully!',
      }
      supportData.value = structuredClone (toRaw (supportDataBase))
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
    supportData.value = structuredClone (toRaw (supportDataBase))
    updateTeams ()
    updateMerchants ()
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
            {{ $t ('tabs.add_support') }}
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
                        v-model="supportData.username"
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
                        v-model="supportData.email"
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
                        v-model="supportData.first_name"
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
                        v-model="supportData.password"
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
                        v-model="supportData.password2"
                        :label="$t('confirm_password')"
                        :type="isConfirmPasswordVisible ? 'text' : 'password'"
                        :append-inner-icon="isConfirmPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                        @click:append-inner="isConfirmPasswordVisible = !isConfirmPasswordVisible"
                      />
                    </VCol>
                  </VRow>
                </VForm>
              </VCardText>
            </VCard>
          </VCol>
          <VCol cols="12">
            <VCard :title="$t('team_setup')">
              <VCardText>
                <VForm @submit.prevent="() => {}">
                  <VRow>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VSelect
                        v-model="supportData.controlled_teams"
                        multiple
                        :items="teams"
                        item-title="name"
                        item-value="id"
                        :loading="teams.length === 0"
                        :label="$t('controlled_teams')"
                        outlined
                        dense
                      />
                    </VCol>
                  </VRow>
                </VForm>
              </VCardText>
            </VCard>
          </VCol>
          <VCol cols="12">
            <VCard :title="$t('merchant_setup')">
              <VCardText>
                <VForm @submit.prevent="() => {}">
                  <VRow>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VSelect
                        v-model="supportData.controlled_merchants"
                        multiple
                        :items="merchants"
                        item-title="username"
                        item-value="id"
                        :loading="teams.length === 0"
                        :label="$t('controlled_merchants')"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
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

