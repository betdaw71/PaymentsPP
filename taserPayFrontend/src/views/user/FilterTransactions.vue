<script setup>
import { useTradeStore } from "@/stores/useTradeStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { useBaseStore } from "@/stores/useBaseStore"
import { useMerchantStore } from "@/stores/useMerchantStore"

const props = defineProps ({
  data: {
    type: Object,
    required: false,
    default: () => {
      return {
        'balance__available__user__username__in': [],
        'balance__available_merchant__user__username__in': [],
        'balance__available__team__name__in': [],
        'balance__type__in': [],
      }
    },
  },
  type: {
    type: String,
    required: false,
    default: "from",
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
  'update:data',
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
const data = ref (structuredClone (toRaw (props.data)))

watch (props, () => {
  data.value = structuredClone (toRaw (props.data))
})

const filters = ref ({
  "merchants": [],
  "system": [],
  "teams": [],
  "traders": [],
})

const getBalanceTargets = () => {
  (authStore.is_support() ? baseStore.getSupportBalanceTargets ({}) : baseStore.getTraderBalanceTargets({})).then (
    response => {
      if (response.error) {
        throw response.error
      }
      filters.value = response.data
    }).catch (error => {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: error,
    }
  })
}

const onFormSubmit = async () => {
  emit ('update:data', data.value)
  emit ('update:isDialogVisible', false)
}

const onFormReset = () => {
  data.value = structuredClone (toRaw (props.data))
  emit ('update:isDialogVisible', false)
}

const dialogModelValueUpdate = val => {
  emit ('update:isDialogVisible', val)
}

onMounted (
  () => {
    getBalanceTargets ()
  },
)

const switchSelection = (values, name, key) => {
  try {
    console.log({
      data_vals: data.value,
      data_vals_named:data.value[name],
      values,
      name,
    })
    if (data.value[name].length !== 0) {
      data.value[name] = []
    } else {
      data.value[name] = JSON.parse (JSON.stringify (values.map (item => item[key])))
    }
    console.log({
      data_vals: data.value,
      data_vals_named:data.value[name],
      values,
      name,
    })
  } catch(e){
    console.log({ e })
    console.log({
      data_vals: data.value,
      data_vals_named:data.value[name],
      values,
      name,
    })
  }
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
          {{ t ('filter_transactions.title') }} ({{ props.type.toUpperCase () }})
        </VCardTitle>
        <p class="mb-0">
          {{ t ('filter_transactions.description') }}
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
              v-if="authStore.is_support() || authStore.is_senior_trader()"
              cols="12"
              md="6"
            >
              <VSelect
                v-model="data.balance__available__user__username__in"
                multiple
                clearable
                clear-icon="tabler-x"
                :items="filters.traders"
                item-title="name"
                item-value="value"
                :loading="filters.traders.length === 0"
                :label="t ('filter_transactions.traders')"
                outlined
                dense
                :prepend-inner-icon="data.balance__available__user__username__in.length === filters.traders.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                @click:prepend-inner="switchSelection(filters.traders, 'balance__available__user__username__in', 'name')"
              />
            </VCol>
            <VCol
              v-if="authStore.is_head_of_support()"
              cols="12"
              md="6"
            >
              <VSelect
                v-model="data.balance__available_merchant__user__username__in"
                multiple
                clearable
                clear-icon="tabler-x"
                :items="filters.merchants"
                item-title="name"
                item-value="value"
                :loading="filters.merchants.length === 0"
                :label="t ('filter_transactions.merchants')"
                outlined
                dense
                :prepend-inner-icon="data.balance__available_merchant__user__username__in.length === filters.merchants.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                @click:prepend-inner="switchSelection(filters.merchants, 'balance__available_merchant__user__username__in', 'name')"
              />
            </VCol>
            <VCol
              v-if="authStore.is_support()"
              cols="12"
              md="6"
            >
              <VSelect
                v-model="data.balance__available__team__name__in"
                multiple
                clearable
                clear-icon="tabler-x"
                :items="filters.teams"
                item-title="name"
                item-value="value"
                :loading="filters.teams.length === 0"
                :label="t ('filter_transactions.teams')"
                outlined
                dense
                :prepend-inner-icon="data.balance__available__team__name__in.length === filters.teams.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                @click:prepend-inner="switchSelection(filters.teams, 'balance__available__team__name__in', 'name')"
              />
            </VCol>
            <VCol
              v-if="authStore.is_support()"
              cols="12"
              md="6"
            >
              <VSelect
                v-model="data.balance__type__in"
                multiple
                clearable
                clear-icon="tabler-x"
                :items="filters.system"
                item-title="name"
                item-value="value"
                :loading="filters.system.length === 0"
                :label="t ('filter_transactions.system')"
                outlined
                dense
                :prepend-inner-icon="data.balance__type__in.length === filters.system.length ? 'tabler-square-check-filled': 'tabler-square-check'"
                @click:prepend-inner="switchSelection(filters.system, 'balance__type__in', 'value')"
              />
            </VCol>
            <VCol
              cols="12"
              class="d-flex flex-wrap justify-center gap-4"
            >
              <VBtn
                type="submit"
              >
                {{ t ('merchant_edit_dialog.submit_btn') }}
              </VBtn>

              <VBtn
                color="secondary"
                variant="tonal"
                @click="onFormReset"
              >
                {{ t ('merchant_edit_dialog.reset_btn') }}
              </VBtn>
            </VCol>
          </VRow>
        </VForm>
      </VCardText>
    </VCard>
  </VDialog>
</template>
