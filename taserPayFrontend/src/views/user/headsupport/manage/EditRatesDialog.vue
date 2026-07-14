<script setup>
import { useTradeStore } from "@/stores/useTradeStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { useBaseStore } from "@/stores/useBaseStore"
import { requiredValidator, uniqueValidator } from "@validators"

const props = defineProps ({
  data: {
    type: Object,
    required: false,
    default: () => {
      return {
        team_id: "",
        team_name: "",
        fees: [],
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

const feeBase = computed (
  () => {
    return {
      mdr_in: 0,
      mdr_out: 0,
      team: props.data.team_id,
    }
  },
)

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const authStore = useAuthStore ()
const baseStore = useBaseStore ()
const tradeStore = useTradeStore ()
const fees = ref ({})
const data = ref (structuredClone (toRaw (props.data)))
const paymentSystems = ref ([])
const trafficTypes = ref ([])

watch (props, () => {
  data.value = structuredClone (toRaw (props.data))
}, { deep: true })

const saveAllPaymentSystems = () => {
  data.value.fees.forEach (
    async (fee, index) => {
      if (!fee.id) {
        await savePaymentSystem(index)
      }
    },
  )
}

const onFormSubmit = async () => {
  await saveAllPaymentSystems ()
}

const onFormReset = () => {
  data.value.fees = data.value.fees.filter(fee => fee.id)
}

const dialogModelValueUpdate = val => {
  emit ('update:isDialogVisible', val)
}

const updatePaymentSystems = () => {
  baseStore.getPaymentSystem ({}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      paymentSystems.value = response.data
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
    updatePaymentSystems ()
  },
)

const availablePaymentSystems = computed (() => {
  return paymentSystems.value.filter (item => {
    return data.value.fees.filter (fee => {
      return fee.payment_system === item.id
    }).length === 0
  })
})

const addPaymentSystem = () => {
  data.value.fees.push (structuredClone (toRaw (feeBase.value)))
}

const removePaymentSystem = index => {
  data.value.fees[index].loading = true
  if (!data.value.fees[index]?.id)
    return data.value.fees.splice (index, 1)
  tradeStore.deleteRate ({}, data.value.fees[index].id).then (
    response => {
      if (response.error) {
        throw response.error
      }
      data.value.fees.splice (index, 1)
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

const savePaymentSystem = index => {
  data.value.fees[index].loading = true
  tradeStore.createRate ({
    ...data.value.fees[index],
  }).then (
    response => {
      if (response.error) {
        throw response.error
      }
      data.value.fees[index] = response.data
      data.value.fees[index].loading = false
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error.message,
      }
      data.value.fees[index].loading = false
    },
  )
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
          {{ t ('rates_edit_dialog.title') }} @{{ data.team_name }}
        </VCardTitle>
        <p class="mb-0">
          {{ t ('rates_edit_dialog.description') }}
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
            <VRow>
              <VCol
                cols="12"
              >
                <VCard
                  v-for="(fee, index) in data.fees"
                  :key="index"
                  class="ma-2 w-100"
                  :loading="fee?.loading"
                >
                  <VToolbar
                    color="rgb(255,255,255)"
                    dark
                    flat
                  >
                    <VToolbarTitle>
                      {{ $t ('payment_system') + ` ${index + 1}` }}
                    </VToolbarTitle>
                    <template #append>
                      <VBtn
                        v-if="!fee.id"
                        size="30"
                        color="success"
                        variant="flat"
                        class="me-1"
                        icon
                        @click="savePaymentSystem (index)"
                      >
                        <VIcon
                          size="18"
                          icon="tabler-device-floppy"
                          color="white"
                        />
                      </VBtn>
                      <VBtn
                        size="30"
                        color="error"
                        variant="flat"
                        icon
                        @click="removePaymentSystem (index)"
                      >
                        <VIcon
                          size="18"
                          icon="tabler-trash"
                          color="white"
                        />
                      </VBtn>
                    </template>
                  </VToolbar>
                  <VDivider color="secondary" />
                  <VCardText>
                    <VRow>
                      <VCol
                        cols="12"
                        sm="6"
                      >
                        <VTextField
                          v-model="fee.mdr_in"
                          :label="$t('rate_in')"
                          outlined
                          dense
                          :rules="[
                            requiredValidator
                          ]"
                          :disabled="fee.id"
                        />
                      </VCol>
                      <VCol
                        cols="12"
                        sm="6"
                      >
                        <VTextField
                          v-model="fee.mdr_out"
                          :label="$t('rate_out')"
                          outlined
                          dense
                          :rules="[
                            requiredValidator
                          ]"
                          :disabled="fee.id"
                        />
                      </VCol>
                      <VCol
                        cols="12"
                      >
                        <VSelect
                          v-model="fee.payment_system"
                          :items="!fee.id ?
                            [...availablePaymentSystems, ...paymentSystems.filter(item => item.id === fee.payment_system)]
                            : paymentSystems"
                          item-title="name"
                          item-value="id"
                          :loading="paymentSystems.length === 0"
                          :label="t ('payment_systems')"
                          prepend-inner-icon="tabler-cash"
                          outlined
                          dense
                          :rules="[
                            uniqueValidator (data.fees, index, 'payment_system', $t ('payment_system')),
                            requiredValidator
                          ]"
                          scroll-strategy="close"
                          :disabled="fee.id"
                        />
                      </VCol>
                    </VRow>
                  </VCardText>
                </VCard>
              </VCol>
              <VCol
                cols="12"
              >
                <VBtn
                  v-if="availablePaymentSystems.length !== 0"
                  class="w-100"
                  variant="outlined"
                  color="primary"
                  append-icon="tabler-plus"
                  @click="addPaymentSystem"
                >
                  {{ $t ('add_supported_payment_system') }}
                </VBtn>
                <VAlert
                  v-else
                  icon="tabler-checks"
                  variant="tonal"
                  color="success"
                  class="ma-4"
                >
                  <VAlertTitle class="mb-1">
                    {{ $t ('alerts.no_more_payment_systems_available.title') }}
                  </VAlertTitle>
                  <span>
                    {{ $t ('alerts.no_more_payment_systems_available.description') }}
                  </span>
                </VAlert>
              </VCol>
            </VRow>
            <VCol
              cols="12"
              class="d-flex flex-wrap justify-center gap-4"
            >
              <VBtn
                type="submit"
              >
                {{ t ('rates_edit_dialog.submit_btn') }}
              </VBtn>

              <VBtn
                color="secondary"
                variant="tonal"
                @click="onFormReset"
              >
                {{ t ('rates_edit_dialog.reset_btn') }}
              </VBtn>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>
    </VCard>
  </VDialog>
</template>
