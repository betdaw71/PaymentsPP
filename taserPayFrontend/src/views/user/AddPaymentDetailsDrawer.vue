<script setup>
import { PerfectScrollbar } from 'vue3-perfect-scrollbar'
import {
  regexValidator,
  requiredValidator,
} from '@validators'
import { useTradeStore } from "@/stores/useTradeStore"
import {
  capitalize, formatTimeDelta, formatTimeDeltaSeconds,
  resolveOrderInStatusVariantAndIcon,
} from "@core/utils/formatters"
import { useAuthStore } from "@/stores/useAuthStore"
import { useBaseStore } from "@/stores/useBaseStore"
import PaymentDetails from "@/views/user/PaymentDetails.vue"

const props = defineProps ({
  isDrawerOpen: {
    type: Boolean,
    required: true,
  },
  time: {
    type: Number,
    required: true,
  },
})

const emit = defineEmits ([
  'update:isDrawerOpen',
  'update:items',
])

const { t } = useI18n ()

const baseStore = useBaseStore ()

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

const payment_system_options = ref ({})
const system_field_required = ref (false)

const baseData = ref ({
  payment_system: null,
  currency: null,
  owner: "",
  min_amount_out: 0,
  max_amount_out: 10000,
  allowed_traffic: [],
  in_active: false,
  out_active: false,
  work_type: "by_card",
})


const currentFields = ref ({})

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})


const tradeStore = useTradeStore ()
const authStore = useAuthStore ()


const isFormValid = ref (false)
const refForm = ref ()

const detailsBaseData = computed (() => {
  if (itemData.value.payment_system) {
    console.log({ currentFields: currentFields.value })

    return {
      ...Object.keys(currentFields.value).reduce ((acc, key) => {
        acc[key] = currentFields.value[key]?.type === "bool" ? false : ""

        return acc
      }, {}),
    }
  }

  return {}
})

const closeNavigationDrawer = () => {
  emit ('update:isDrawerOpen', false)
  nextTick (() => {
    refForm.value?.reset ()
    refForm.value?.resetValidation ()
  })
}


const handleDrawerModelValueUpdate = val => {
  emit ('update:isDrawerOpen', val)
}

const itemData = ref (structuredClone (toRaw (baseData.value)))

watch (
  () => itemData.value.work_type,
  () => {
    console.log({ work_type: itemData.value.work_type })
  },
  { deep: true },
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

const saveItem = async () => {
  const result = await refForm.value.validate ()
  if (!result?.valid) {
    console.log ("validation error")

    return
  }
  console.log ("validation success")
  baseStore.createPaymentDetails ({
    ...itemData.value,
  }).then (
    response => {
      if (response.error) {
        throw response.error
      }
      snackbar.value = {
        enabled: true,
        message: `${t ('payment_system')} ${t ('created')}!`,
        type: "success",
      }
      closeNavigationDrawer ()
      emit ('update:items')
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

const resetItemData = async () => {
  itemData.value = structuredClone (toRaw (baseData.value))
  system_field_required.value = false
  nextTick (() => {
    refForm.value?.reset ()
    refForm.value?.resetValidation ()
  })
}

watch (
  () => itemData.value.payment_system,
  () => {
    if (itemData.value.payment_system) {
      console.log ({ itemData: itemData.value })
      currentFields.value = structuredClone (toRaw (payment_system_options.value[itemData.value.payment_system]))
      console.log ({ currentFields: currentFields.value })
      itemData.value.details = []

      // itemData.value.details = Object.fromEntries (currentFields.value.map (field => [field, ""]))
    }
  },
  { deep: true },
)
onMounted (
  () => {
    getGroupCreationData ()
    getCreationData ()
  },
)

const switchSelection = (values, name, key) => {
  if (itemData.value[name].length !== 0) {
    itemData.value[name] = []
  } else {
    itemData.value[name] = JSON.parse (JSON.stringify (values.map (item => item[key])))
  }
}

const addDetails = () => {
  const tmpId = Math.random ().toString (36).substring (2, 15) + Math.random ().toString (36).substring (2, 15)

  itemData.value.details.push ({
    ...structuredClone (toRaw (detailsBaseData.value)),
    tmpId: tmpId,
  })
}

const removeDetail = index => {
  itemData.value.details.splice (index, 1)
}

const saveDetail = index => {}

const updateDetail = (index, data) => {
  console.log ({ index, data })
  itemData.value.details[index] = data
}
</script>

<template>
  <VNavigationDrawer
    temporary
    :width="400"
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
      :title="$t('payment_details_creation')"
      @cancel="closeNavigationDrawer"
    >
      <template #beforeClose>
        <VSpacer />
        <VBtn
          icon="tabler-deselect"
          size="small"
          @click="resetItemData"
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
              <VCol cols="12">
                <VTextField
                  v-model="itemData.owner"
                  :label="$t('owner')"
                  :rules="[
                    requiredValidator,
                  ]"
                />
              </VCol>
              <VCol
                v-if="itemData.work_type === 'by_deposit_number' || itemData.work_type === 'by_cash'"
                cols="12"
              >
                <VTextField
                  v-model="itemData.bic"
                  :label="$t('bic')"
                  :rules="[
                    requiredValidator,
                  ]"
                />
              </VCol>
              <VCol cols="12">
                <AppSelect
                  v-model="itemData.payment_system"
                  :label="$t('payment_system')"
                  :items="options.payment_systems"
                  item-title="name"
                  item-value="id"
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
                  multiple
                  clearable
                  clear-icon="tabler-x"
                  :prepend-inner-icon="itemData.allowed_traffic.length === options.traffic_types.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                  @click:prepend-inner="switchSelection(options.traffic_types, 'allowed_traffic', 'id')"
                />
              </VCol>
              <VCol cols="12">
                <AppSelect
                  v-model="itemData.work_type"
                  :label="$t('work_type')"
                  :items="workTypes"
                  :item-title="(item) => $t(item)"
                  :item-value="(item) => item"
                  :rules="[
                    requiredValidator
                  ]"
                />
              </VCol>
              <VCol cols="12">
                <VSwitch
                  v-model="itemData.in_active"
                  :label="$t('in_active')"
                />
              </VCol>
              <VCol cols="12">
                <VSwitch
                  v-model="itemData.out_active"
                  :label="$t('out_active')"
                />
              </VCol>
              <VCol cols="6">
                <VTextField
                  v-model="itemData.min_amount_out"
                  :label="$t('min_amount_out')"
                  :rules="[
                    requiredValidator
                  ]"
                />
              </VCol>
              <VCol cols="6">
                <VTextField
                  v-model="itemData.max_amount_out"
                  :label="$t('max_amount_out')"
                  :rules="[
                    requiredValidator
                  ]"
                />
              </VCol>
              <VCardText v-if="itemData.payment_system">
                <div
                  v-for="(detail, index) in itemData.details"
                  :key="detail.tmpId"
                  class="my-4 ma-sm-4"
                >
                  <PaymentDetails
                    :id="index"
                    type="creation"
                    :work-type="itemData.work_type"
                    :fields="currentFields"
                    :data="detail"
                    @save="saveDetail"
                    @remove="removeDetail"
                    @update="updateDetail"
                  />
                </div>
              </VCardText>
              <VCol
                v-if="itemData.payment_system"
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
                cols="12"
              >
                <VBtn
                  class="w-100"
                  color="primary"
                  @click="saveItem"
                >
                  {{ $t ('save') }}
                </VBtn>
              </VCol>
            </VRow>
          </VForm>
        </VCardText>
      </VCard>
    </PerfectScrollbar>
  </VNavigationDrawer>
</template>
