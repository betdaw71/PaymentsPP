<script setup>
import { useMerchantStore } from '@/stores/useMerchantStore'
import { useBaseStore } from '@/stores/useBaseStore'
import { betweenValidator, requiredValidator } from '@validators'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  assignment: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'saved'])

const merchantStore = useMerchantStore()
const baseStore = useBaseStore()

const isLoading = ref(false)
const merchants = ref([])
const teamLeads = ref([])

const form = ref({
  merchant: null,
  agent: null,
  turnover_percent_in: '0.5',
  turnover_percent_out: '0.5',
  is_active: true,
})

const normalizeList = data => {
  if (data?.results)
    return data.results
  return Array.isArray(data) ? data : []
}

const resetForm = () => {
  if (props.assignment) {
    form.value = {
      merchant: props.assignment.merchant,
      agent: props.assignment.agent,
      turnover_percent_in: String(props.assignment.turnover_percent_in),
      turnover_percent_out: String(props.assignment.turnover_percent_out),
      is_active: props.assignment.is_active,
    }
  } else {
    form.value = {
      merchant: null,
      agent: null,
      turnover_percent_in: '0.5',
      turnover_percent_out: '0.5',
      is_active: true,
    }
  }
}

watch(() => props.modelValue, open => {
  if (open) {
    resetForm()
    merchantStore.getMerchant({ per_page: 500 }).then(r => {
      if (!r.error)
        merchants.value = normalizeList(r.data)
    })
    baseStore.getTeamLead({ per_page: 200 }).then(r => {
      if (!r.error)
        teamLeads.value = normalizeList(r.data)
    })
  }
})

const close = () => emit('update:modelValue', false)

const submit = () => {
  isLoading.value = true
  const payload = {
    merchant: form.value.merchant,
    agent: form.value.agent,
    turnover_percent_in: form.value.turnover_percent_in,
    turnover_percent_out: form.value.turnover_percent_out,
    is_active: form.value.is_active,
  }

  const req = props.assignment
    ? merchantStore.patchMerchantAgentAssignment(payload, props.assignment.id)
    : merchantStore.createMerchantAgentAssignment(payload)

  req.then(response => {
    isLoading.value = false
    if (response.error)
      throw response.error
    emit('saved')
    close()
  }).catch(err => {
    isLoading.value = false
    console.error(err)
  })
}
</script>

<template>
  <VDialog
    :model-value="modelValue"
    max-width="560"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <VCard>
      <VCardTitle>
        {{ assignment ? $t('merchant_agent.edit_title') : $t('merchant_agent.add_title') }}
      </VCardTitle>
      <VCardText>
        <VRow>
          <VCol cols="12">
            <AppSelect
              v-model="form.merchant"
              :label="$t('merchant')"
              :items="merchants"
              item-title="username"
              item-value="id"
              :disabled="!!assignment"
              :rules="[requiredValidator]"
            />
          </VCol>
          <VCol cols="12">
            <AppSelect
              v-model="form.agent"
              :label="$t('team_lead')"
              :items="teamLeads"
              item-title="name"
              item-value="id"
              :rules="[requiredValidator]"
            />
          </VCol>
          <VCol
            cols="12"
            sm="6"
          >
            <AppTextField
              v-model="form.turnover_percent_in"
              type="number"
              :label="$t('merchant_agent.turnover_in')"
              :rules="[requiredValidator, v => betweenValidator(v, 0, 100)]"
            />
          </VCol>
          <VCol
            cols="12"
            sm="6"
          >
            <AppTextField
              v-model="form.turnover_percent_out"
              type="number"
              :label="$t('merchant_agent.turnover_out')"
              :rules="[requiredValidator, v => betweenValidator(v, 0, 100)]"
            />
          </VCol>
          <VCol cols="12">
            <VSwitch
              v-model="form.is_active"
              :label="$t('active')"
            />
          </VCol>
        </VRow>
      </VCardText>
      <VCardActions>
        <VSpacer />
        <VBtn
          variant="text"
          @click="close"
        >
          {{ $t('cancel') }}
        </VBtn>
        <VBtn
          color="primary"
          :loading="isLoading"
          @click="submit"
        >
          {{ $t('save') }}
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>
