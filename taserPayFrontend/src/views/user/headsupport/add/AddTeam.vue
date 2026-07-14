<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { betweenValidator, requiredValidator } from "@validators"

const authStore = useAuthStore ()
const baseStore = useBaseStore ()
const isLoading = ref (false)


const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const itemDataBase = {
  name: "",
  rate_in: 0,
  rate_out: 0,
  teamlead_rate: 0.0,
  teamleads: [],
  insurance_deposit: 0,
}


const itemData = ref (structuredClone (toRaw (itemDataBase)))

const teams = ref ([])
const teamLeads = ref ([])
const currencies = ref ([])

const createItem = () => {
  isLoading.value = true
  baseStore.createTraderTeam ({
    ...itemData.value,
  }).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: 'Team created successfully!',
      }
      itemData.value = structuredClone (toRaw (itemDataBase))
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

const getTeamLeads = () => {
  baseStore.getTeamLead ().then (
    response => {
      if (response.error) {
        throw response.error
      }
      teamLeads.value = response.data
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

onMounted (
  () => {
    itemData.value = structuredClone (toRaw (itemDataBase))
    getTeamLeads ()
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
              icon="tabler-users"
            />
            {{ $t ('tabs.add_team') }}
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
                    >
                      <VTextField
                        v-model="itemData.name"
                        :label="$t('team_name')"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="itemData.rate_in"
                        :label="$t('rate_in')"
                        type="number"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="itemData.rate_out"
                        :label="$t('rate_out')"
                        type="number"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="itemData.insurance_deposit"
                        :label="$t('insurance_deposit')"
                        type="number"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VTextField
                        v-model="itemData.teamlead_rate"
                        :label="$t('teamlead_rate')"
                        type="number"
                        :rules="[requiredValidator, betweenValidator (itemData.teamlead_rate, 0, 100)]"
                        append-inner-icon="tabler-percentage"
                        outlined
                        dense
                      />
                    </VCol>
                    <VCol
                      cols="12"
                      sm="6"
                    >
                      <VSelect
                        v-model="itemData.teamleads"
                        multiple
                        :items="teamLeads"
                        item-title="name"
                        item-value="id"
                        :loading="teamLeads.length === 0"
                        :label="$t('teamleads')"
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
                        @click="createItem"
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

