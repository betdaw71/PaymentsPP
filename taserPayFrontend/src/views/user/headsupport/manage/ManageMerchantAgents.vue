<script setup>
import { useMerchantStore } from '@/stores/useMerchantStore'
import MerchantAgentAssignmentDialog from '@/views/user/headsupport/manage/MerchantAgentAssignmentDialog.vue'

const merchantStore = useMerchantStore()

const snackbar = ref({
  enabled: false,
  type: 'error',
  message: '',
})

const items = ref([])
const isDialogVisible = ref(false)
const editItem = ref(null)

const normalizeList = data => {
  if (data?.results)
    return data.results
  return Array.isArray(data) ? data : []
}

const load = () => {
  merchantStore.getMerchantAgentAssignments({ per_page: 200 }).then(response => {
    if (response.error) {
      snackbar.value = { enabled: true, type: 'error', message: String(response.error) }
      return
    }
    items.value = normalizeList(response.data)
  })
}

const openCreate = () => {
  editItem.value = null
  isDialogVisible.value = true
}

const openEdit = row => {
  editItem.value = structuredClone(toRaw(row))
  isDialogVisible.value = true
}

const onSaved = () => {
  isDialogVisible.value = false
  load()
}

onMounted(() => {
  load()
})
</script>

<template>
  <div>
    <VSnackbar
      v-model="snackbar.enabled"
      :color="snackbar.type"
      :timeout="3000"
      location="top"
    >
      {{ snackbar.message }}
    </VSnackbar>

    <VCard>
      <VCardTitle class="mt-2 ms-2 d-flex align-center flex-wrap gap-2">
        <VAvatar
          size="50"
          variant="text"
          color="primary"
          icon="tabler-users-group"
        />
        {{ $t('tabs.manage_merchant_agents') }}
        <VSpacer />
        <VBtn
          color="primary"
          size="small"
          prepend-icon="tabler-plus"
          @click="openCreate"
        >
          {{ $t('merchant_agent.add') }}
        </VBtn>
        <VBtn
          icon="tabler-refresh"
          size="small"
          variant="text"
          @click="load"
        />
      </VCardTitle>

      <VCardText>
        <VTable>
          <thead>
            <tr>
              <th>{{ $t('merchant') }}</th>
              <th>{{ $t('team_lead') }}</th>
              <th>{{ $t('merchant_agent.turnover_in') }}</th>
              <th>{{ $t('merchant_agent.turnover_out') }}</th>
              <th>{{ $t('status') }}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in items"
              :key="row.id"
            >
              <td>{{ row.merchant_username }}</td>
              <td>{{ row.agent_username }}</td>
              <td>{{ row.turnover_percent_in }}%</td>
              <td>{{ row.turnover_percent_out }}%</td>
              <td>
                <VChip
                  size="small"
                  :color="row.is_active ? 'success' : 'secondary'"
                  variant="tonal"
                >
                  {{ row.is_active ? $t('active') : $t('inactive') }}
                </VChip>
              </td>
              <td class="text-end">
                <VBtn
                  icon="tabler-pencil"
                  size="small"
                  variant="text"
                  @click="openEdit(row)"
                />
              </td>
            </tr>
            <tr v-if="items.length === 0">
              <td
                colspan="6"
                class="text-center text-medium-emphasis py-6"
              >
                {{ $t('data.empty') }}
              </td>
            </tr>
          </tbody>
        </VTable>
      </VCardText>
    </VCard>

    <MerchantAgentAssignmentDialog
      v-model="isDialogVisible"
      :assignment="editItem"
      @saved="onSaved"
    />
  </div>
</template>
