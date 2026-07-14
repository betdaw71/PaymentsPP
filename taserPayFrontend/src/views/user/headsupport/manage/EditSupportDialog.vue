<script setup>
import { useTradeStore } from "@/stores/useTradeStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { useBaseStore } from "@/stores/useBaseStore"
import { requiredValidator } from "@validators"
import { useMerchantStore } from "@/stores/useMerchantStore"

const props = defineProps ({
  userData: {
    type: Object,
    required: false,
    default: () => {
      return {
        id: "",
        controlled_teams: [],
        controlled_merchants: [],
      }
    },
  },
  isDialogVisible: {
    type: Boolean,
    required: true,
  },
})

const emit = defineEmits ([
  'update',
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
const baseStore = useBaseStore ()
const merchantStore = useMerchantStore ()
const userData = ref (structuredClone (toRaw (props.userData)))
const teams = ref ([])
const merchants = ref ([])

watch (props, () => {
  userData.value = structuredClone (toRaw (props.userData))
})

const editUser = () => {
  baseStore.updateSupportMemberById ({
    controlled_teams: userData.value.controlled_teams,
    controlled_merchants: userData.value.controlled_merchants,
  }, userData.value.id).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        type: 'success',
        message: t ('support_edit_dialog.success'),
      }

      emit ('update', true)
      setTimeout (() => {
        emit ('update:isDialogVisible', false)
      }, 1500)
    }).catch (error => {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: error,
    }
  })
}

const onFormSubmit = async () => {
  await editUser ()
}

const onFormReset = () => {
  userData.value = structuredClone (toRaw (props.userData))
  emit ('update:isDialogVisible', false)
}

const dialogModelValueUpdate = val => {
  emit ('update:isDialogVisible', val)
}

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

onMounted (
  () => {
    updateTeams ()
    updateMerchants ()
  },
)
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
          {{ t ('support_edit_dialog.title') }} @{{ userData.username }}
        </VCardTitle>
        <p class="mb-0">
          {{ t ('support_edit_dialog.description') }}
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
              <VSelect
                v-model="userData.controlled_teams"
                multiple
                :items="teams"
                item-title="name"
                item-value="id"
                :loading="teams.length === 0"
                :label="t ('support_edit_dialog.controlled_teams')"
                prepend-inner-icon="tabler-vector-triangle"
                outlined
                dense
              />
            </VCol>
            <VCol
              cols="12"
            >
              <VSelect
                v-model="userData.controlled_merchants"
                multiple
                :items="merchants"
                item-title="username"
                item-value="id"
                :loading="merchants.length === 0"
                :label="t ('support_edit_dialog.controlled_merchants')"
                prepend-inner-icon="tabler-vector-triangle"
                outlined
                dense
              />
            </VCol>
            <VCol
              cols="12"
              class="d-flex flex-wrap justify-center gap-4"
            >
              <VBtn
                type="submit"
              >
                {{ t ('support_edit_dialog.submit_btn') }}
              </VBtn>

              <VBtn
                color="secondary"
                variant="tonal"
                @click="onFormReset"
              >
                {{ t ('support_edit_dialog.reset_btn') }}
              </VBtn>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>
    </VCard>
  </VDialog>
</template>
