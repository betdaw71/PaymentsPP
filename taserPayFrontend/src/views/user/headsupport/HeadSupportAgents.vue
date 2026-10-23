<script setup>
import { useBaseStore } from "@/stores/useBaseStore"

const baseStore = useBaseStore()

const snackbar = ref({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const agents = ref([])
const teamleads = ref([])

const fail = error => {
  snackbar.value = { enabled: true, type: 'error', message: error }
}

const updateAgents = () => {
  Promise.all([
    baseStore.getBalanceSupportAgent({}),
    baseStore.getBalanceSupportTeamlead({}),
  ]).then(([agentRes, teamleadRes]) => {
    if (agentRes.error) {
      fail(agentRes.error)
      return
    }
    if (teamleadRes.error) {
      fail(teamleadRes.error)
      return
    }
    agents.value = agentRes.data || []
    teamleads.value = teamleadRes.data || []
  }).catch(error => {
    fail(error)
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
        <div class="text-subtitle-1 font-weight-medium mb-2">
          {{ $t('roles.agent') }}
        </div>
        <VList>
          <VListItem v-if="!agents.length">
            <VListItemTitle class="text-medium-emphasis">
              {{ $t('no_agents') }}
            </VListItemTitle>
          </VListItem>
          <VListItem
            v-for="item in agents"
            :key="item.id"
          >
            <VListItemTitle class="d-flex flex-wrap align-center ga-1">
              <span class="font-weight-bold me-1">@{{ item.username }}</span>
              <VChip
                color="warning"
                size="small"
              >
                {{ $t('agent_debt') }}: ${{ Number(item.debt).toFixed(2) }}
              </VChip>
              <VChip
                color="info"
                size="small"
              >
                {{ item.commission_percent }}%
              </VChip>
              <VChip
                v-for="name in item.merchants"
                :key="name"
                color="secondary"
                size="small"
              >
                {{ name }}
              </VChip>
            </VListItemTitle>
          </VListItem>
        </VList>

        <VDivider class="my-4" />

        <div class="text-subtitle-1 font-weight-medium mb-2">
          {{ $t('tabs.team_leads') }}
        </div>
        <VList>
          <VListItem v-if="!teamleads.length">
            <VListItemTitle class="text-medium-emphasis">
              {{ $t('no_teamleads') }}
            </VListItemTitle>
          </VListItem>
          <VListItem
            v-for="item in teamleads"
            :key="item.id"
          >
            <VListItemTitle class="d-flex flex-wrap align-center ga-1">
              <span class="font-weight-bold me-1">@{{ item.username }}</span>
              <VChip
                color="warning"
                size="small"
              >
                {{ $t('teamlead_balance') }}: ${{ Number(item.debt).toFixed(2) }}
              </VChip>
              <VChip
                v-if="Number(item.frozen)"
                color="info"
                size="small"
              >
                {{ $t('frozen_balance') }}: ${{ Number(item.frozen).toFixed(2) }}
              </VChip>
              <VChip
                v-if="item.commission_percent"
                color="primary"
                size="small"
              >
                {{ item.commission_percent }}%
              </VChip>
              <VChip
                v-for="team in item.teams"
                :key="team.name"
                color="secondary"
                size="small"
              >
                {{ team.name }}
                <template v-if="!item.commission_percent && team.percentage">
                  · {{ team.percentage }}%
                </template>
              </VChip>
            </VListItemTitle>
          </VListItem>
        </VList>
      </VCardText>
    </VCard>
  </div>
</template>
