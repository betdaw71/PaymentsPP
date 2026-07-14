<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { requiredValidator } from "@validators"

const authStore = useAuthStore ()
const baseStore = useBaseStore ()
const isLoading = ref (false)
const isBoss = ref (false)


const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const traderDataBase = {
  username: "",
  password: "",
  password2: "",
  email: "",
  first_name: "",
  boss: null,
  team: null,
  currency: null,

  // address: null,
}


const traderData = ref (structuredClone (toRaw (traderDataBase)))

const teams = ref ([])
const currencies = ref ([])
const bossList = ref ([])

const isNewPasswordVisible = ref (false)
const isConfirmPasswordVisible = ref (false)

const updateTeams = ({ currency }) => {
  baseStore.getTraderTeam (currency ? { currency } : {}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      teams.value = response.data
      if (teams.value.length > 0) {
        traderData.value.team = teams.value[0].id
      }
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

const getBoss = () => {
  baseStore.getTrader ({
    team: traderData.value.team,
    is_boss: true,
  }).then (
    response => {
      if (response.error) {
        throw response.error
      }
      bossList.value = response.data
      if (bossList.value.length > 0) {
        traderData.value.boss = bossList.value[0].id
      }
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

const updateCurrencies = () => {
  baseStore.getCurrency ({}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      currencies.value = response.data
      if (currencies.value.length > 0) {
        traderData.value.currency = currencies.value[0].id
      }
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
  authStore.registerTrader ({
    ...traderData.value,
    boss: isBoss.value ? null : traderData.value.boss,

    // is_boss: isBoss.value,
  }).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: 'Trader created successfully!',
      }
      isLoading.value = false
      traderData.value = structuredClone (toRaw (traderDataBase))
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
    traderData.value = structuredClone (toRaw (traderDataBase))
    updateTeams ({ currency: null })
    updateCurrencies ()
  },
)
watchEffect (
  () => {
    console.log ({
      teams: teams.value,
    })
  },
)
watch(
  () => {
    return traderData.value.currency
  },
  () => {
    updateTeams({ currency: traderData.value.currency })
  },
)
watch (
  () => {
    return traderData.value.team
  },
  () => {
    if (traderData.value.team) {
      getBoss ()
    }
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
            {{ $t ('tabs.add_trader') }}
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
                        v-model="traderData.username"
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
                        v-model="traderData.email"
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
                        v-model="traderData.first_name"
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
                        v-model="traderData.password"
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
                        v-model="traderData.password2"
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
            <!-- 👉 Change password -->
            <VCard :title="$t('team_setup')">
              <VCardText>
                <VForm @submit.prevent="() => {}">
                  <VRow>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VSelect
                        v-model="traderData.currency"
                        :items="currencies"
                        item-title="name"
                        item-value="id"
                        :loading="currencies.length === 0"
                        :label="$t('currency')"
                        :rules="[
                          requiredValidator
                        ]"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VSelect
                        v-model="traderData.team"
                        :items="teams"
                        item-title="name"
                        item-value="id"
                        :loading="teams.length === 0"
                        :label="$t('team')"
                        :rules="[
                          requiredValidator
                        ]"
                        outlined
                        dense
                      />
                    </VCol>
                  </VRow>
                  <VRow>
                    <VCol
                      cols="12"
                      sm="3"
                    >
                      <VSwitch
                        v-model="isBoss"
                        :label="$t('is_boss')"
                        color="primary"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      v-show="!isBoss"
                      cols="12"
                      sm="4"
                    >
                      <VSelect
                        v-model="traderData.boss"
                        :items="bossList"
                        item-title="username"
                        item-value="id"
                        :loading="bossList.length === 0"
                        :label="$t('boss')"
                        :rules="[
                          requiredValidator
                        ]"
                        outlined
                        dense
                      />
                    </VCol>
                    <!--                    <VCol -->
                    <!--                      v-show="isBoss" -->
                    <!--                      cols="12" -->
                    <!--                      sm="5" -->
                    <!--                    > -->
                    <!--                      <VTextField -->
                    <!--                        v-model="traderData.address" -->
                    <!--                        :label="$t('address')" -->
                    <!--                        outlined -->
                    <!--                        dense -->
                    <!--                      /> -->
                    <!--                    </VCol> -->
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

