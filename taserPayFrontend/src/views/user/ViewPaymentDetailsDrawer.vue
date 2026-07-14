<script setup>
import { PerfectScrollbar } from 'vue3-perfect-scrollbar'
import {
  requiredValidator,
} from '@validators'
import { useTradeStore } from "@/stores/useTradeStore"
import {
  capitalize, formatTimeDelta, formatTimeDeltaSeconds,
  resolvePaymentDetailsStatusVariantAndIcon,
} from "@core/utils/formatters"
import { useAuthStore } from "@/stores/useAuthStore"
import { useBaseStore } from "@/stores/useBaseStore"
import PaymentDetails from "@/views/user/PaymentDetails.vue"


const props = defineProps ({
  isDrawerOpen: {
    type: Boolean,
    required: true,
  },
  itemId: {
    type: String,
    required: false,
    default: null,
  },
  time: {
    type: Number,
    required: true,
  },
})

const emit = defineEmits ([
  'update:isDrawerOpen',
])

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const tradeStore = useTradeStore ()
const authStore = useAuthStore ()
const baseStore = useBaseStore ()


const isFormValid = ref (false)
const refForm = ref ()

const { t } = useI18n()

const currentFields = computed(
  () => structuredClone(toRaw(payment_system_options.value[itemData.value.payment_system] || {})),
)


const closeNavigationDrawer = () => {
  emit ('update:isDrawerOpen', false)
  nextTick (() => {
    refForm.value?.reset ()
    refForm.value?.resetValidation ()
  })
}

const itemData = ref ({
  id: null,
})

const getItemById = async id => {
  itemData.value = {
    id: null,
  }
  baseStore.getPaymentDetailsById ({}, id)
    .then (response => {
      if (response.error) {
        throw response.error
      }
      itemData.value = response.data
    }).catch (error => {
      console.log (error)
      snackbar.value = {
        enabled: true,
        type: "error",
        message: error,
      }
    })
}

const payment_system_options = ref ({})

const workTypes = ref([
  "by_card",
  "by_cash",
  "by_deposit_number",
])

const options = ref ({
  payment_systems: [],
  traffic_types: [],
  currencies: [],
})

const getGroupCreationData = async () => {
  baseStore.getPaymentDetailsGroupCreationData ({}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      options.value = response.data
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        message: error,
        type: "error",
      }
    },
  )
}

const getCreationData = async () => {
  baseStore.getPaymentDetailsCreationData ({}).then (
    response => {
      if (response.error) {
        throw response.error
      }
      payment_system_options.value = response.data
    },
  ).catch (
    error => {
      snackbar.value = {
        enabled: true,
        message: error,
        type: "error",
      }
    },
  )
}

watch (
  () => itemData.value.payment_system,
  () => {
    if (itemData.value.payment_system) {
      console.log ({ itemData: itemData.value })
      currentFields.value = structuredClone (toRaw (payment_system_options.value[itemData.value.payment_system]))
      console.log ({ currentFields: currentFields.value })
    }
  },
  { deep: true },
)

watchEffect (
  async () => {
    if (props.itemId) {
      await getGroupCreationData ()
      await getCreationData ()
      getItemById (props.itemId)
    }
  },
)

const handleDrawerModelValueUpdate = val => {
  emit ('update:isDrawerOpen', val)
}



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

const changeWorkStatus = async status => {
  baseStore.changePaymentDetailsWorkStatusById ({
    status,
  }, props.itemId).then (response => {
    if (response.error) {
      throw response.error
    }
    snackbar.value = {
      enabled: true,
      type: "success",
      message: "Status changed successfully!",
    }
  }).catch (error => {
    console.log (error)
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
    getItemById (props.itemId)
  })
}

const changeBlockStatus = async block => {
  baseStore.changePaymentDetailsWorkStatusById ({
    status: block ? 3 : 1,
  }, props.itemId).then (response => {
    if (response.error) {
      throw response.error
    }
    snackbar.value = {
      enabled: true,
      type: "success",
      message: `Status changed to "${block ? t('blocked_by_support') : t('not_blocked_by_support')}" successfully!`,
    }
  }).catch (error => {
    console.log (error)
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
    getItemById (props.itemId)
  })
}

const changeDepositMode = async mode => {
  baseStore.changePaymentDetailsDepositModeById ({
    on: mode,
  }, props.itemId).then (response => {
    if (response.error) {
      throw response.error
    }
    snackbar.value = {
      enabled: true,
      type: "success",
      message: `${mode ? t('deposit_number_on') : t('deposit_number_off')}`,
    }
  }).catch (error => {
    console.log (error)
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
    getItemById (props.itemId)
  })
}

const archive = async () => {
  baseStore.changePaymentDetailsWorkStatusById ({
    status: 2,
  }, props.itemId).then (response => {
    if (response.error) {
      throw response.error
    }
    snackbar.value = {
      enabled: true,
      type: "success",
      message: `Details archived successfully!`,
    }
  }).catch (error => {
    console.log (error)
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
  }).then(
    () => {
      getItemById (props.itemId)
    },
  )
}

const arbitrageUnlock = async () => {
  baseStore.changePaymentDetailsArbitrageUnblockStatusById ({}, props.itemId).then (response => {
    if (response.error) {
      throw response.error
    }
    snackbar.value = {
      enabled: true,
      type: "success",
      message: "Arbitrage Unblocked successfully!",
    }
    itemData.value.arbitrage_blocked = false
  }).catch (error => {
    console.log (error)
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
    getItemById (props.itemId)
  })
}

const changeStatus = (item, status) => {
  // 0 - in_active
  // 1 - out_active
  // 2 - both
  const data = { status: 2 }
  if (item.in_active) { // prev - 0
    if (item.out_active) { // prev - 2
      if (status === "in") { // out - true, in - false
        data.status = 1
      } else { // out - false, in - true
        data.status = 0
      }
    } else { // prev - 0
      if (status === "in") { // out - false, in - false
        data.status = 1
      } else { // out - true, in - true
        data.status = 2
      }
    }
  } else { // prev - 1
    if (item.out_active) { // prev - 2
      if (status === "in") { // out - true, in - true
        data.status = 2
      } else { // out - false, in - true
        data.status = 0
      }
    } else { // prev - -1
      if (status === "in") { // out - false, in - true
        data.status = 0
      } else { // out - true, in - false
        data.status = 1
      }
    }
  }
  baseStore.changePaymentDetailsDirectionStatusById(data, item.id).then (response => {
    if (response.error) {
      throw response.error
    }
    if (data.status === 2) {
      itemData.value.in_active = true
      itemData.value.out_active = true
    } else if (data.status === 1) {
      itemData.value.in_active = false
      itemData.value.out_active = true
    } else {
      itemData.value.in_active = true
      itemData.value.out_active = false
    }
    snackbar.value = {
      enabled: true,
      type: "success",
      message: t ('success') + "!",
    }
  }).catch (error => {
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
  })
}

const detailsBaseData = computed (() => {
  if (itemData.value.payment_system) {
    console.log({ currentFields: currentFields.value })

    return {
      ...Object.keys(currentFields.value).reduce ((acc, key) => {
        acc[key] = currentFields.value[key] === "bool"? false : ""

        return acc
      }, {}),
    }
  }

  return {}
})


const addDetails = () => {
  itemData.value.details.push (structuredClone (toRaw (detailsBaseData.value)))
}

const removeDetail = index => {
  if (itemData.value.details[index].id) {
    baseStore.changePaymentDetailToDetailsById({
      status: 2,
      details: itemData.value.details[index].id,
    },  itemData.value.id).then (response => {
      if (response.error) {
        throw response.error
      }
      itemData.value.details.splice (index, 1)
      snackbar.value = {
        enabled: true,
        type: "success",
        message: "Detail removed successfully!",
      }
    }).catch (error => {
      snackbar.value = {
        enabled: true,
        type: "error",
        message: error,
      }
    })
  }
  else {
    itemData.value.details.splice (index, 1)
  }
}

const saveDetail = (index, data) => {
  console.log ({ index, data })
  baseStore.addPaymentDetailToDetailsById({
    ...data,
  }, itemData.value.id).then (response => {
    if (response.error) {
      throw response.error
    }
    itemData.value.details[index] = response.data
    snackbar.value = {
      enabled: true,
      type: "success",
      message: "Detail saved successfully!",
    }
  }).catch (error => {
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
  })
}

const updateLimits = () => {
  baseStore.updatePaymentDetailLimitsById({
    min_amount_out: itemData.value.min_amount_out,
    max_amount_out: itemData.value.max_amount_out,
    volume_in: itemData.value.volume_in,
  }, itemData.value.id).then (response => {
    if (response.error) {
      throw response.error
    }
    snackbar.value = {
      enabled: true,
      type: "success",
      message: "Limits updated successfully!",
    }
  }).catch (error => {
    snackbar.value = {
      enabled: true,
      type: "error",
      message: error,
    }
  })

}

const updateDetail = (index, data) => {
  itemData.value.details[index] = data
}

const switchSelection = (values, name, key) => {
  if (itemData.value[name].length !== 0) {
    itemData.value[name] = []
  } else {
    itemData.value[name] = JSON.parse (JSON.stringify (values.map (item => item[key])))
  }
}
</script>

<template>
  <VNavigationDrawer
    temporary
    :width="600"
    location="end"
    class="scrollable-content"
    :model-value="props.isDrawerOpen"
    @update:model-value="handleDrawerModelValueUpdate"
  >
    <VSnackbar
      v-model="snackbar.enabled"
      :color="snackbar.type"
      :timeout="3000"
      top
    >
      {{ snackbar.message }}
    </VSnackbar>
    <AppDrawerHeaderSection
      :title="$t('payment_details')"
      @cancel="closeNavigationDrawer"
    >
      <template #beforeClose>
        <VSpacer />
        <VBtn
          icon="tabler-refresh"
          size="small"
          @click="getItemById(props.itemId)"
        />
      </template>
    </AppDrawerHeaderSection>

    <PerfectScrollbar :options="{ wheelPropagation: false }">
      <VCard flat>
        <VCardText>
          <!-- 👉 Form -->
          <VForm
            ref="refForm"
            v-model="isFormValid"
          >
            <VRow>
              <VCol
                v-if="!itemData.id"
                cols="12"
              >
                {{ $t('loading') }}&nbsp;
                <VProgressCircular
                  :width="3"
                  color="primary"
                  indeterminate
                />
              </VCol>
              <template v-else>
                <VCol
                  class="d-flex justify-center align-center"
                  cols="12"
                >
                  <VChip
                    :color="resolvePaymentDetailsStatusVariantAndIcon(itemData.status).variant"
                    variant="tonal"
                  >
                    {{ resolvePaymentDetailsStatusVariantAndIcon (itemData.status).text }}
                  </VChip>
                  <VTooltip
                    location="top"
                  >
                    <template #activator="{ props }">
                      <VBtn
                        v-bind="props"
                        size="xs"
                        class="ms-2"
                        :color="itemData.arbitrage_blocked ? 'error': 'success'"
                        :icon="itemData.arbitrage_blocked ? 'tabler-circle-x' : 'tabler-circle-check'"
                      />
                    </template>
                    <span>
                      {{ itemData.arbitrage_blocked ? $t ('arbitrage_blocked') : $t ('no_arbitrage') }}
                    </span>
                  </VTooltip>
                  <VTooltip
                    location="top"
                  >
                    <template #activator="{ props }">
                      <VBtn
                        v-bind="props"
                        size="xs"
                        class="ms-2"
                        :color="itemData.blocked_by_support ? 'error': 'success'"
                        :icon="itemData.blocked_by_support ? 'tabler-circle-x' : 'tabler-circle-check'"
                      />
                    </template>
                    <span>
                      {{ itemData.blocked_by_support ? $t ('blocked_by_support') : $t ('not_blocked_by_support') }}
                    </span>
                  </VTooltip>
                  <VTooltip
                    location="top"
                  >
                    <template #activator="{ props }">
                      <VBtn
                        v-bind="props"
                        size="xs"
                        class="ms-2"
                        :color="itemData.out_active ? 'success': 'error'"
                        icon="tabler-circle-arrow-up-right"
                        :disabled="!authStore.is_trader() && !authStore.is_head_of_support()"
                        @click.stop="changeStatus(itemData, 'out')"
                      />
                    </template>
                    <span>
                      {{ itemData.out_active ? $t ('out_active') : $t ('out_not_active') }}
                    </span>
                  </VTooltip>
                  <VTooltip
                    location="top"
                  >
                    <template #activator="{ props }">
                      <VBtn
                        v-bind="props"
                        size="xs"
                        class="ms-2"
                        :color="itemData.in_active ? 'success': 'error'"
                        icon="tabler-circle-arrow-down-left"
                        :disabled="!authStore.is_trader() && !authStore.is_head_of_support()"
                        @click.stop="changeStatus(itemData, 'in')"
                      />
                    </template>
                    <span>
                      {{ itemData.in_active ? $t ('in_active') : $t ('in_not_active') }}
                    </span>
                  </VTooltip>
                </VCol>
                <VCol cols="12">
                  <VTextField
                    v-model="itemData.id"
                    :label="$t ('id')"
                    readonly
                    append-inner-icon="tabler-clipboard"
                    @click:append-inner="copyToClipboard(itemData.id, `ID copied to clipboard!`, 'success')"
                  />
                </VCol>
                <VCol cols="12">
                  <VTextField
                    v-model="itemData.owner"
                    :label="$t('owner')"
                    :rules="[
                      requiredValidator,
                    ]"
                    readonly
                    append-inner-icon="tabler-clipboard"
                    @click:append-inner="copyToClipboard(itemData.owner, $t('copied_to_clipboard', {value: $t(`owner`)}), 'success')"
                  />
                </VCol>
                <VCol
                  v-if="itemData.work_type === 'by_deposit_number'"
                  cols="12"
                >
                  <VTextField
                    v-model="itemData.bic"
                    :label="$t('bic')"
                    :rules="[
                      requiredValidator,
                    ]"
                    readonly
                    append-inner-icon="tabler-clipboard"
                    @click:append-inner="copyToClipboard(itemData.owner, $t('copied_to_clipboard', {value: $t(`bic`)}), 'success')"
                  />
                </VCol>
                <VCol cols="12">
                  <AppSelect
                    v-model="itemData.work_type"
                    :label="$t('work_type')"
                    :items="workTypes"
                    :item-title="(item) => $t(item)"
                    :rules="[
                      requiredValidator
                    ]"
                    disabled
                  />
                </VCol>
                <VCol cols="12">
                  <AppSelect
                    v-model="itemData.payment_system"
                    :label="$t('payment_system')"
                    :items="options.payment_systems"
                    item-title="name"
                    item-value="id"
                    disabled
                    :rules="[
                      requiredValidator
                    ]"
                  />
                </VCol>
                <VCol cols="12">
                  <AppSelect
                    v-model="itemData.currency"
                    :label="$t('currency')"
                    :items="options.currencies"
                    item-title="name"
                    item-value="id"
                    disabled
                    :rules="[
                      requiredValidator
                    ]"
                  />
                </VCol>
                <VCol cols="12">
                  <AppSelect
                    v-model="itemData.allowed_traffic"
                    :label="$t('allowed_traffic_types')"
                    :items="options.traffic_types"
                    item-title="name"
                    item-value="id"
                    disabled
                    multiple
                    clearable
                    clear-icon="tabler-x"
                    :prepend-inner-icon="itemData.allowed_traffic.length === options.traffic_types.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                    @click:prepend-inner="switchSelection(options.traffic_types, 'allowed_traffic', 'id')"
                  />
                </VCol>
                <VCol cols="6">
                  <VTextField
                    v-model="itemData.min_amount_out"
                    :label="$t('min_amount_out')"
                    :rules="[
                      requiredValidator
                    ]"
                    :disabled="!authStore.is_support()"
                  />
                </VCol>
                <VCol cols="6">
                  <VTextField
                    v-model="itemData.max_amount_out"
                    :label="$t('max_amount_out')"
                    :rules="[
                      requiredValidator
                    ]"
                    :disabled="!authStore.is_support()"
                  />
                </VCol>
                <VCol cols="6">
                  <VTextField
                    v-model="itemData.volume_in"
                    :label="$t('volume_in')"
                    :rules="[
                      requiredValidator
                    ]"
                    :disabled="!authStore.is_support()"
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_support()"
                  cols="12"
                >
                  <VBtn
                    class="w-100"
                    color="primary"
                    @click="updateLimits"
                  >
                    {{ $t('update_limits') }}
                  </VBtn>
                </VCol>
                <VCardText v-if="itemData.payment_system">
                  <div
                    v-for="(detail, index) in itemData.details"
                    :key="index"
                    class="my-4 ma-sm-4"
                  >
                    <PaymentDetails
                      :id="index"
                      type="view"
                      :work-type="itemData.work_type"
                      :fields="currentFields"
                      :data="itemData.details[index]"
                      @save="saveDetail"
                      @remove="removeDetail"
                      @update="updateDetail"
                    />
                  </div>
                </VCardText>
                <VCol
                  v-if="itemData.payment_system && authStore.is_trader()"
                  cols="12"
                >
                  <VBtn
                    class="w-100"
                    variant="outlined"
                    color="primary"
                    append-icon="tabler-plus"
                    @click="addDetails"
                  >
                    {{ $t ('add_payment_detail') }}
                  </VBtn>
                </VCol>
                <VCol
                  v-if="itemData.status !== 2"
                  cols="12"
                >
                  <VSwitch
                    v-model="itemData.status"
                    :label="itemData.status === 1 ? $t('active') : $t('inactive')"
                    :true-value="1"
                    :false-value="0"
                    @change="changeWorkStatus(itemData.status)"
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_support()"
                  cols="12"
                >
                  <VSwitch
                    v-model="itemData.blocked_by_support"
                    :label="itemData.blocked_by_support ? $t('blocked_by_support') : $t('unblocked')"
                    @change="changeBlockStatus(itemData.blocked_by_support)"
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_head_of_support() && itemData.arbitrage_blocked"
                  cols="12"
                >
                  <VBtn
                    class="w-100"
                    color="success"
                    @click="arbitrageUnlock"
                  >
                    {{ $t('arb_unlock') }}
                  </VBtn>
                </VCol>
                <VCol
                  v-if="(authStore.is_support() || authStore.is_trader()) && itemData.status !== 2"
                  cols="12"
                >
                  <VBtn
                    class="w-100"
                    color="alternative"
                    @click="archive"
                  >
                    {{ $t('archive') }}
                  </VBtn>
                </VCol>
              </template>
            </VRow>
          </VForm>
        </VCardText>
      </VCard>
    </PerfectScrollbar>
  </VNavigationDrawer>
</template>
