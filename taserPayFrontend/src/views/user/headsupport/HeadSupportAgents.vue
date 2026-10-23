<script setup>
import { useBaseStore } from "@/stores/useBaseStore"

const baseStore = useBaseStore()

const snackbar = ref({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const agents = ref([])

const updateAgents = () => {
  baseStore.getBalanceSupportAgent({}).then(
    response => {
      if (response.error) {
        snackbar.value = { enabled: true, type: 'error', message: response.error }
        return
      }
      agents.value = response.data
    },
  ).catch(error => {
    snackbar.value = { enabled: true, type: 'error', message: error }
  })
}

onMounted(() => {
  updateAgents()
})
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
    <VCard>
      <VCardTitle class="mt-2 ms-2">
        <VAvatar
          size="50"
          variant="text"
          color="primary"
          icon="tabler-percentage"
        />
        {{ $t('tabs.agents') }}
        <VBtn
          class="float-end"
          icon="tabler-refresh"
          size="small"
          @click="updateAgents"
        />
      </VCardTitle>
      <VCardText>
        <VList>
          <VListItem
            v-for="item in agents"
            :key="item.id"
          >
            <VListItemTitle>
              <span class="font-weight-bold">@{{ item.username }}</span>
              <VChip
                class="ms-1 p-1"
                color="warning"
                small
              >
                {{ $t('agent_debt') }}: ${{ Number(item.debt).toFixed(2) }}
              </VChip>
              <VChip
                class="ms-1 p-1"
                color="info"
                small
              >
                {{ item.commission_percent }}%
              </VChip>
              <VChip
                v-for="name in item.merchants"
                :key="name"
                class="ms-1 p-1"
                color="secondary"
                small
              >
                {{ name }}
              </VChip>
            </VListItemTitle>
          </VListItem>
        </VList>
      </VCardText>
    </VCard>
  </div>
</template>
