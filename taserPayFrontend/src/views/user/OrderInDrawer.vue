<script setup>
import { PerfectScrollbar } from 'vue3-perfect-scrollbar'
import {
  requiredValidator,
} from '@validators'
import { useTradeStore } from "@/stores/useTradeStore"
import {
  capitalize, formatTimeDelta, formatTimeDeltaSeconds,
  resolveOrderInStatusVariantAndIcon,
} from "@core/utils/formatters"
import { useAuthStore } from "@/stores/useAuthStore"

const props = defineProps ({
  isDrawerOpen: {
    type: Boolean,
    required: true,
  },
  orderId: {
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
  'userData',
])

const isCancelAgain = ref (false)
const isCompleteAgain = ref (false)
const isRecalculateAgain = ref (false)
const isMoveAgain = ref (false)
const isCallbackAgain = ref (false)
const isArbitrageAgain = ref (false)
const fileArbitrage = ref (null)

const resetOthers = current => {
  isCancelAgain.value = current === 'isCancelAgain'
  isMoveAgain.value = current === 'isMoveAgain'
  isCompleteAgain.value = current === 'isCompleteAgain'
  isRecalculateAgain.value = current === 'isRecalculateAgain'
  isCallbackAgain.value = current === 'isCallbackAgain'
  isArbitrageAgain.value = current === 'isArbitrageAgain'
}

watch(isCancelAgain, newValue => {
  if (newValue) resetOthers('isCancelAgain')
})
watch(isMoveAgain, newValue => {
  if (newValue) resetOthers('isMoveAgain')
})
watch(isCompleteAgain, newValue => {
  if (newValue) resetOthers('isCompleteAgain')
})
watch(isRecalculateAgain, newValue => {
  if (newValue) resetOthers('isRecalculateAgain')
})
watch(isCallbackAgain, newValue => {
  if (newValue) resetOthers('isCallbackAgain')
})
watch(isArbitrageAgain, newValue => {
  if (newValue) resetOthers('isArbitrageAgain')
})

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const tradeStore = useTradeStore ()
const authStore = useAuthStore ()


const isFormValid = ref (false)
const refForm = ref ()
const reasons = ref ([])

const extra_fields = ref ({
  recalculate_amount: 0,
  move_details: '',
  rejection_reason: 'no-pay',
})

const closeNavigationDrawer = () => {
  emit ('update:isDrawerOpen', false)
  nextTick (() => {
    refForm.value?.reset ()
    refForm.value?.resetValidation ()
    resetAllAgainButtons ()
  })
}

const resetAllAgainButtons = () => {
  console.log('resetAllAgainButtons')
  isCancelAgain.value = false
  isCompleteAgain.value = false
  isRecalculateAgain.value = false
  isMoveAgain.value = false
  isCallbackAgain.value = false
  isArbitrageAgain.value = false
}

const order_data = ref ({
  id: null,
})

const getOrderById = async id => {
  order_data.value = {
    id: null,
  }
  tradeStore.getTradeOrderInById ({}, id)
    .then (response => {
      if (response.error) {
        throw response.error
      }
      order_data.value = response.data
    }).catch (error => {
      console.log (error)
      snackbar.value = {
        enabled: true,
        type: "error",
        message: error,
      }
    })
}

watchEffect (
  () => {
    if (props.orderId) {
      getOrderById (props.orderId)
      resetAllAgainButtons ()
      if (authStore.is_trader()) {
        getReasons ()
      }
    }
  },
)

const handleDrawerModelValueUpdate = val => {
  emit ('update:isDrawerOpen', val)
  resetAllAgainButtons ()
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

const completeSupport = () => {
  if (order_data.value.id) {
    tradeStore.changeTradeOrderInCompleteSupportById ({}, order_data.value.id)
      .then (response => {
        if (response.error) {
          throw response.error
        }
        snackbar.value = {
          enabled: true,
          type: "success",
          message: "Completed by support!",
        }
        getOrderById (order_data.value.id)
      }).catch (error => {
        console.log (error)
        snackbar.value = {
          enabled: true,
          type: "error",
          message: error,
        }
      })
  }
}

const complete = () => {
  if (order_data.value.id) {
    tradeStore.changeTradeOrderInCompleteById ({}, order_data.value.id)
      .then (response => {
        if (response.error) {
          throw response.error
        }
        snackbar.value = {
          enabled: true,
          type: "success",
          message: "Completed!",
        }
        getOrderById (order_data.value.id)
      }).catch (error => {
        console.log (error)
        snackbar.value = {
          enabled: true,
          type: "error",
          message: error,
        }
      })
  }
}

const cancel = () => {
  if (order_data.value.id) {
    tradeStore.changeTradeOrderInCancelById ({
      trader_comment: extra_fields.value.rejection_reason,
    }, order_data.value.id)
      .then (response => {
        if (response.error) {
          throw response.error
        }
        snackbar.value = {
          enabled: true,
          type: "success",
          message: "Cancel by support!",
        }
        getOrderById (order_data.value.id)
      }).catch (error => {
        console.log (error)
        snackbar.value = {
          enabled: true,
          type: "error",
          message: error,
        }
      })
  }
}

const arbitrageSupport = () => {
  if (order_data.value.id) {
    let form = new FormData()
    form.append('file', fileArbitrage.value[0], "file.pdf")
    tradeStore.changeTradeOrderInArbitrageSupportById (form, order_data.value.id)
      .then (response => {
        if (response.error) {
          throw response.error
        }
        snackbar.value = {
          enabled: true,
          type: "success",
          message: "Arbitrage by support!",
        }
        getOrderById (order_data.value.id)
      }).catch (error => {
        console.log (error)
        snackbar.value = {
          enabled: true,
          type: "error",
          message: error,
        }
      })
  }
}

const getReasons = async () => {
  tradeStore.getReasonsOrderIn ({})
    .then (response => {
      if (response.error) {
        throw response.error
      }
      reasons.value = response.data
    }).catch (error => {
      console.log (error)
      snackbar.value = {
        enabled: true,
        type: "error",
        message: error,
      }
    })
}

const recalculate = async () => {
  if (order_data.value.id) {
    tradeStore.recalculateTradeOrderInById ({
      amount: extra_fields.value.recalculate_amount,
    }, order_data.value.id)
      .then (response => {
        if (response.error) {
          throw response.error
        }
        snackbar.value = {
          enabled: true,
          type: "success",
          message: "Recalculation completed!",
        }
        getOrderById (order_data.value.id)
      }).catch (error => {
        console.log (error)
        snackbar.value = {
          enabled: true,
          type: "error",
          message: error,
        }
      })
  }
}

const move = async () => {
  if (order_data.value.id) {
    tradeStore.moveTradeOrderInById ({
      details: extra_fields.value.move_details,
    }, order_data.value.id)
      .then (response => {
        if (response.error) {
          throw response.error
        }
        snackbar.value = {
          enabled: true,
          type: "success",
          message: "Movement completed!",
        }
        getOrderById (order_data.value.id)
      }).catch (error => {
        console.log (error)
        snackbar.value = {
          enabled: true,
          type: "error",
          message: error,
        }
      })
  }
}

const callback = () => {
  if (order_data.value.id) {
    tradeStore.changeTradeOrderInCallbackById ({}, order_data.value.id)
      .then (response => {
        if (response.error) {
          throw response.error
        }
        snackbar.value = {
          enabled: true,
          type: "success",
          message: "Callback sent!",
        }
        getOrderById (order_data.value.id)
      }).catch (error => {
        console.log (error)
        snackbar.value = {
          enabled: true,
          type: "error",
          message: error,
        }
      })
  }
}
</script>

<template>
  <VNavigationDrawer
    temporary
    :width="700"
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
      :title="$t('order_in')"
      @cancel="closeNavigationDrawer"
    >
      <template #beforeClose>
        <VSpacer />
        <VBtn
          icon="tabler-refresh"
          size="small"
          @click="getOrderById(props.orderId)"
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
                v-if="!order_data.id"
                cols="12"
              >
                {{ $t ('loading') }}&nbsp;
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

                    :color="resolveOrderInStatusVariantAndIcon(order_data.status).variant"
                    variant="tonal"
                  >
                    {{ resolveOrderInStatusVariantAndIcon (order_data.status).text }}
                  </VChip>
                  <VTooltip
                    v-if="!authStore.is_merchant() && order_data.auto_closed"
                    location="right"
                  >
                    <template #activator="{ props }">
                      <VIcon
                        v-bind="props"
                        color="error"
                        icon="tabler-robot-face"
                      />
                    </template>
                    <span>
                      {{ $t ('auto_closed') }}
                    </span>
                  </VTooltip>
                </VCol>
                <VCol cols="12">
                  <VTextField
                    v-model="order_data.id"
                    :label="$t ('id')"
                    readonly
                    append-inner-icon="tabler-clipboard"
                    @click:append-inner="copyToClipboard(order_data.id, `ID copied to clipboard!`, 'success')"
                  />
                </VCol>
                <VCol cols="6">
                  <VTextField
                    v-model="order_data.amount"
                    :label="$t ('amount')"
                    :suffix="order_data.currency"
                    readonly
                  />
                </VCol>
                <VCol cols="6">
                  <VTextField
                    v-model="order_data.usd_amount"
                    :label="$t ('usd_amount')"
                    suffix="$"
                    readonly
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_support() || authStore.is_trader() || authStore.is_team_lead()"
                  cols="6"
                >
                  <VTextField
                    v-model="order_data.trader_fee"
                    :label="$t ('trader_fee')"
                    suffix="$"
                    readonly
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_support() || authStore.is_merchant_admin() || authStore.is_merchant_assist()"
                  cols="6"
                >
                  <VTextField
                    v-model="order_data.merchant_fee"
                    :label="$t ('merchant_fee')"
                    suffix="$"
                    readonly
                  />
                </VCol>
                <VCol
                  v-if="order_data.pic && (authStore.is_support() || authStore.is_trader())"
                  cols="6"
                >
                  <VBtn
                    :href="order_data.pic"
                    target="_blank"
                    rel="noopener noreferrer"
                    color="primary"
                  >
                    {{ $t ('receipt_image') }}
                  </VBtn>
                </VCol>
                <VCol
                  v-if="authStore.is_support() || authStore.is_merchant_assist() || authStore.is_merchant_admin()"
                  cols="12"
                >
                  <VTextField
                    v-model="order_data.customer_id"
                    :label="$t ('customer_id')"
                    readonly
                    append-inner-icon="tabler-clipboard"
                    @click:append-inner="copyToClipboard(order_data.customer_id, $t('copied_to_clipboard', {value: $t('customer_id')}), 'success')"
                  />
                </VCol>

                <VExpansionPanels
                  v-if="!authStore.is_team_lead()"
                  class="mt-3 px-5 pb-5"
                >
                  <VExpansionPanel>
                    <VExpansionPanelTitle>
                      <div class="text-h6">
                        {{ $t ('payment_details') }}
                      </div>
                    </VExpansionPanelTitle>
                    <VExpansionPanelText>
                      <VCol cols="12">
                        <VTextField
                          v-model="order_data.payment_system"
                          :label="$t('payment_system')"
                          readonly
                        />
                      </VCol>
                      <VCol cols="12">
                        <VTextField
                          v-model="order_data.payment_details_id"
                          :label="$t ('payment_details_id')"
                          readonly
                          append-inner-icon="tabler-clipboard"
                          @click:append-inner="copyToClipboard(order_data.payment_details_id, `Payment Details ID copied to clipboard!`, 'success')"
                        />
                      </VCol>
                      <template
                        v-if="authStore.is_support() || authStore.is_trader() || authStore.is_merchant_assist() || authStore.is_merchant_admin()"
                      >
                        <VCol
                          v-for="(detail, name) in order_data.payment_details"
                          :key="name"
                          cols="12"
                        >
                          <VTextField
                            :model-value="detail"
                            :label="$t('details') + ` [` + $t(`fields.${name}`) + `]`"
                            readonly
                            append-inner-icon="tabler-clipboard"
                            @click:append-inner="copyToClipboard(detail, `${capitalize(name)} copied to clipboard!`, 'success')"
                          />
                        </VCol>
                      </template>
                    </VExpansionPanelText>
                  </VExpansionPanel>
                </VExpansionPanels>
                <VCol
                  v-if="authStore.is_support() || authStore.is_trader()"
                  cols="12"
                >
                  <VTextField
                    v-model="order_data.traffic_type"
                    :label="$t('traffic_type')"
                    readonly
                  />
                </VCol>

                <VCol
                  v-if="['Cancelled', 'Cancelled by trader','Cannot process'].indexOf(order_data.status) !== -1 && !authStore.is_team_lead()"
                  cols="12"
                >
                  <VTextField
                    :value="$t (`comments.${order_data?.rejection_reason?.toLowerCase()}`)"
                    :label="$t ('rejection_reason')"
                    readonly
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_support() || authStore.is_senior_trader()"
                  cols="12"
                >
                  <VTextField
                    :model-value="`@${order_data.trader}`"
                    :label="$t ('trader')"
                    readonly
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_support() && order_data.status === 'Recalculation'"
                  cols="12"
                >
                  <VTextField
                    :model-value="order_data.recalculated_amount"
                    :label="$t ('recalculated_amount')"
                    readonly
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_head_of_support()"
                  cols="12"
                >
                  <VTextField
                    :model-value="`@${order_data.merchant}`"
                    :label="$t ('merchant')"
                    readonly
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_support() || authStore.is_merchant()"
                  cols="12"
                >
                  <VTextField
                    v-model="order_data.merchant_order_id"
                    :label="$t ('merchant_order_id')"
                    readonly
                    append-inner-icon="tabler-clipboard"
                    @click:append-inner="copyToClipboard(order_data.merchant_order_id, `Order ID copied to clipboard!`, 'success')"
                  />
                </VCol>
                <VCol
                  v-if="authStore.is_support()"
                  cols="12"
                >
                  <VBtn
                    class="w-100 mt-1"
                    color="primary"
                    append-icon="tabler-rotate-dot"
                    @click="isCallbackAgain ? callback() : (() => {isCallbackAgain = true})()"
                  >
                    {{ $t ('callback') }} {{ isCallbackAgain ? $t('click_again') : $t('double_click') }}
                  </VBtn>
                </VCol>
                <VCol
                  v-if="order_data.status === 'New'"
                  cols="12"
                >
                  <VBtn
                    v-if="authStore.is_trader()"
                    class="w-100 mt-1"
                    color="success"
                    append-icon="tabler-rosette-discount-check"
                    @click="isCompleteAgain ? complete() : (() => {isCompleteAgain = true})()"
                  >
                    {{ $t ('complete') }} {{ isCompleteAgain ? $t('click_again') : $t('double_click') }}
                  </VBtn>
                  <VCard
                    v-if="authStore.is_support()"
                    class="mt-3"
                    border
                  >
                    <VCardTitle>
                      {{ $t ('movement') }}
                    </VCardTitle>
                    <VCardText>
                      <VRow>
                        <VCol
                          cols="12"
                        >
                          <VTextField
                            v-model="extra_fields.move_details"
                            :label="$t ('move_details')"
                            type="text"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                        >
                          <VBtn
                            class="w-100 mt-1"
                            color="primary"
                            append-icon="tabler-chevrons-right"
                            @click="isMoveAgain ? move() : (() => {isMoveAgain = true})()"
                          >
                            {{ $t ('move') }} {{ isMoveAgain ? $t('click_again') : $t('double_click') }}
                          </VBtn>
                        </VCol>
                      </VRow>
                    </VCardText>
                  </VCard>
                </VCol>
                <VCol
                  v-if="order_data.status === 'Money sent by user'"
                  cols="12"
                >
                  <VBtn
                    v-if="authStore.is_trader()"
                    class="w-100 mt-1"
                    color="success"
                    append-icon="tabler-rosette-discount-check"
                    @click="isCompleteAgain ? complete() : (() => {isCompleteAgain = true})()"
                  >
                    {{ $t ('complete') }} {{ isCompleteAgain ? $t('click_again') : $t('double_click') }}
                  </VBtn>
                </VCol>
                <VCol
                  v-if="order_data.status === 'Arbitrage'"
                  cols="12"
                >
                  <VBtn
                    v-if="authStore.is_trader()"
                    class="w-100 mt-1"
                    color="success"
                    append-icon="tabler-rosette-discount-check"
                    @click="isCompleteAgain ? complete() : (() => {isCompleteAgain = true})()"
                  >
                    {{ $t ('complete') }} {{ isCompleteAgain ? $t('click_again') : $t('double_click') }}
                  </VBtn>
                  <VCard
                    v-if="authStore.is_trader()"
                    class="mt-3"
                    border
                  >
                    <VCardTitle>
                      {{ $t ('cancel') }}
                    </VCardTitle>
                    <VCardText>
                      <VRow>
                        <VCol
                          cols="12"
                        >
                          <VSelect
                            v-model="extra_fields.rejection_reason"
                            :label="$t ('rejection_reason')"
                            :items="reasons"
                            :item-title="option => $t (`comments.${option?.name?.toLowerCase()}`)"
                            item-value="name"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                        >
                          <VBtn
                            class="w-100 mt-1"
                            color="error"
                            append-icon="tabler-cancel"
                            @click="isCancelAgain ? cancel() : (() => {isCancelAgain = true})()"
                          >
                            {{ $t ('cancel') }} {{ isCancelAgain ? $t('click_again') : $t('double_click') }}
                          </VBtn>
                        </VCol>
                      </VRow>
                    </VCardText>
                  </VCard>
                  <VCard
                    v-if="authStore.is_trader()"
                    class="mt-3"
                    border
                  >
                    <VCardTitle>
                      {{ $t ('recalculation') }}
                    </VCardTitle>
                    <VCardText>
                      <VRow>
                        <VCol
                          cols="12"
                        >
                          <VTextField
                            v-model="extra_fields.recalculate_amount"
                            :label="$t ('recalculate_amount')"
                            :suffix="order_data.currency"
                            type="number"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                        >
                          <VBtn
                            class="w-100 mt-1"
                            color="warning"
                            append-icon="tabler-abacus"
                            @click="isRecalculateAgain ? recalculate() : (() => {isRecalculateAgain = true})()"
                          >
                            {{ $t ('recalculate') }} {{ isRecalculateAgain ? $t('click_again') : $t('double_click') }}
                          </VBtn>
                        </VCol>
                      </VRow>
                    </VCardText>
                  </VCard>
                </VCol>
                <VCol
                  v-if="order_data.status === 'Recalculation'"
                  cols="12"
                >
                  <VBtn
                    v-if="authStore.is_support()"
                    class="w-100 mt-1"
                    color="success"
                    append-icon="tabler-rosette-discount-check"
                    @click="isCompleteAgain ? completeSupport() : (() => {isCompleteAgain = true})()"
                  >
                    {{ $t ('complete') }} {{ isCompleteAgain ? $t('click_again') : $t('double_click') }}
                  </VBtn>
                  <VBtn
                    v-if="authStore.is_support()"
                    class="w-100 mt-1"
                    color="error"
                    append-icon="tabler-cancel"
                    @click="isCancelAgain ? cancel() : (() => {isCancelAgain = true})()"
                  >
                    {{ $t ('cancel') }} {{ isCancelAgain ? $t('click_again') : $t('double_click') }}
                  </VBtn>
                  <VCard
                    v-if="authStore.is_support()"
                    class="mt-3"
                    border
                  >
                    <VCardTitle>
                      {{ $t ('recalculation') }}
                    </VCardTitle>
                    <VCardText>
                      <VRow>
                        <VCol
                          cols="12"
                        >
                          <VTextField
                            v-model="extra_fields.recalculate_amount"
                            :label="$t ('recalculate_amount')"
                            :suffix="order_data.currency"
                            type="number"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                        >
                          <VBtn
                            class="w-100 mt-1"
                            color="warning"
                            append-icon="tabler-abacus"
                            @click="isRecalculateAgain ? recalculate() : (() => {isRecalculateAgain = true})()"
                          >
                            {{ $t ('recalculate') }} {{ isRecalculateAgain ? $t('click_again') : $t('double_click') }}
                          </VBtn>
                        </VCol>
                      </VRow>
                    </VCardText>
                  </VCard>
                </VCol>
                <VCol
                  v-if="['Cancelled', 'Expired','Cancelled by trader','Cancelled by support'].indexOf(order_data.status) !== -1"
                  cols="12"
                >
                  <VCard
                    v-if="authStore.is_support()"
                    class="mt-3"
                    border
                  >
                    <VCardTitle>
                      {{ $t ('movement') }}
                    </VCardTitle>
                    <VCardText>
                      <VRow>
                        <VCol
                          cols="12"
                        >
                          <VTextField
                            v-model="extra_fields.move_details"
                            :label="$t ('move_details')"
                            type="text"
                          />
                        </VCol>
                        <VCol
                          cols="12"
                        >
                          <VBtn
                            class="w-100 mt-1"
                            color="primary"
                            append-icon="tabler-chevrons-right"
                            @click="isMoveAgain ? move() : (() => {isMoveAgain = true})()"
                          >
                            {{ $t ('move') }} {{ isMoveAgain ? $t('click_again') : $t('double_click') }}
                          </VBtn>
                        </VCol>
                      </VRow>
                    </VCardText>
                  </VCard>
                  <VCard
                    v-if="authStore.is_support()"
                    class="mt-3"
                    border
                  >
                    <VCardTitle>
                      {{ $t ('arbitrage') }}
                    </VCardTitle>
                    <VCardText>
                      <VRow>
                        <VCol
                          cols="12"
                        >
                          <VFileInput
                            v-model="fileArbitrage"
                            :label="$t ('pdf_file')"
                            accept=".pdf"
                            show-size
                          />
                        </VCol>
                        <VCol
                          cols="12"
                        >
                          <VBtn
                            class="mt-1 w-100"
                            color="warning"
                            append-icon="tabler-sunglasses"
                            @click="isArbitrageAgain ? arbitrageSupport() : (() => {isArbitrageAgain = true})()"
                          >
                            {{ $t ('arbitrage') }} {{ isArbitrageAgain ? $t('click_again') : $t('double_click') }}
                          </VBtn>
                        </VCol>
                      </VRow>
                    </VCardText>
                  </VCard>
                </VCol>
                <!--                <template -->
                <!--                  v-if="authStore.is_trader()" -->
                <!--                > -->
                <!--                  <VCol -->
                <!--                    v-if="confirm_money_received_enabled" -->
                <!--                    cols="12" -->
                <!--                  > -->
                <!--                    <VBtn -->
                <!--                      class="w-100" -->
                <!--                      color="primary" -->
                <!--                      @click="confirmReceivingMoney" -->
                <!--                    > -->
                <!--                      {{ $t ('confirm_receiving_money') }} -->
                <!--                    </VBtn> -->
                <!--                  </VCol> -->
                <!--                  <VCol -->
                <!--                    v-if="order_data.status === 'Money sent by user'" -->
                <!--                    cols="12" -->
                <!--                  > -->
                <!--                    <VBtn -->
                <!--                      class="w-100" -->
                <!--                      color="warning" -->
                <!--                      @click="arbitrage" -->
                <!--                    > -->
                <!--                      {{ $t ('arbitrage') }} -->
                <!--                    </VBtn> -->
                <!--                  </VCol> -->
                <!--                </template> -->
                <!--                <template -->
                <!--                  v-else-if="authStore.is_support() && order_data.status.toLowerCase() === 'arbitrage'" -->
                <!--                > -->
                <!--                  <VCol -->
                <!--                    cols="12" -->
                <!--                  > -->
                <!--                    <VBtn -->
                <!--                      class="w-100" -->
                <!--                      color="primary" -->
                <!--                      @click="completeSupport" -->
                <!--                    > -->
                <!--                      {{ $t ('complete') }} -->
                <!--                    </VBtn> -->
                <!--                  </VCol> -->
                <!--                </template> -->
                <!--                <template -->
                <!--                  v-if="(authStore.is_support() || authStore.is_trader()) && order_data.status.toLowerCase() === 'arbitrage'" -->
                <!--                > -->
                <!--                  <VCol -->
                <!--                    cols="12" -->
                <!--                  > -->
                <!--                    <VBtn -->
                <!--                      class="w-100" -->
                <!--                      color="warning" -->
                <!--                      @click="cancelSupport" -->
                <!--                    > -->
                <!--                      {{ $t ('cancel') }} -->
                <!--                    </VBtn> -->
                <!--                  </VCol> -->
                <!--                </template> -->
                <!--                <template -->
                <!--                  v-else-if="authStore.is_support() && order_data.status.toLowerCase() === 'expired'" -->
                <!--                > -->
                <!--                  <VCol -->
                <!--                    cols="12" -->
                <!--                  > -->
                <!--                    <VBtn -->
                <!--                      class="w-100" -->
                <!--                      color="alternative" -->
                <!--                      @click="arbitrageSupport" -->
                <!--                    > -->
                <!--                      {{ $t ('arbitrage') }} -->
                <!--                    </VBtn> -->
                <!--                  </VCol> -->
                <!--                </template> -->
                <!--                <VCol -->
                <!--                  v-if="authStore.is_support() && order_data.status.toLowerCase() === 'completed'" -->
                <!--                  cols="12" -->
                <!--                > -->
                <!--                  <VCard -->
                <!--                    class="mt-3" -->
                <!--                    border -->
                <!--                  > -->
                <!--                    <VCardTitle> -->
                <!--                      {{ $t ('recalculation') }} -->
                <!--                    </VCardTitle> -->
                <!--                    <VCardText> -->
                <!--                      <VRow> -->
                <!--                        <VCol -->
                <!--                          cols="12" -->
                <!--                        > -->
                <!--                          <VTextField -->
                <!--                            v-model="extra_fields.recalculate_amount" -->
                <!--                            :label="$t ('recalculate_amount')" -->
                <!--                            :suffix="order_data.currency" -->
                <!--                            type="number" -->
                <!--                          /> -->
                <!--                        </VCol> -->
                <!--                        <VCol -->
                <!--                          cols="12" -->
                <!--                        > -->
                <!--                          <VBtn -->
                <!--                            class="w-100" -->
                <!--                            color="error" -->
                <!--                            @click="recalculate" -->
                <!--                          > -->
                <!--                            {{ $t ('recalculate') }} -->
                <!--                          </VBtn> -->
                <!--                        </VCol> -->
                <!--                      </VRow> -->
                <!--                    </VCardText> -->
                <!--                  </VCard> -->
                <!--                </VCol> -->
                <!--                <VCol -->
                <!--                  v-if="authStore.is_support() && order_data.status.toLowerCase() === 'completed'" -->
                <!--                  cols="12" -->
                <!--                > -->
                <!--                  <VCard -->
                <!--                    class="mt-3" -->
                <!--                    border -->
                <!--                  > -->
                <!--                    <VCardTitle> -->
                <!--                      {{ $t ('movement') }} -->
                <!--                    </VCardTitle> -->
                <!--                    <VCardText> -->
                <!--                      <VRow> -->
                <!--                        <VCol -->
                <!--                          cols="12" -->
                <!--                        > -->
                <!--                          <VTextField -->
                <!--                            v-model="extra_fields.move_details" -->
                <!--                            :label="$t ('move_details')" -->
                <!--                            type="text" -->
                <!--                          /> -->
                <!--                        </VCol> -->
                <!--                        <VCol -->
                <!--                          cols="12" -->
                <!--                        > -->
                <!--                          <VBtn -->
                <!--                            class="w-100" -->
                <!--                            color="error" -->
                <!--                            @click="move" -->
                <!--                          > -->
                <!--                            {{ $t ('move') }} -->
                <!--                          </VBtn> -->
                <!--                        </VCol> -->
                <!--                      </VRow> -->
                <!--                    </VCardText> -->
                <!--                  </VCard> -->
                <!--                </VCol> -->
              </template>
            </VRow>
          </VForm>
        </VCardText>
      </VCard>
    </PerfectScrollbar>
  </VNavigationDrawer>
</template>
