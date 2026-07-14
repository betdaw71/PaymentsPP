<script setup>
import { useBaseStore } from "@/stores/useBaseStore"
import { useAuthStore } from "@/stores/useAuthStore"
import { requiredValidator } from "@validators"
import { useMerchantStore } from "@/stores/useMerchantStore"
import EditMerchantDialog from "@/views/user/headsupport/manage/EditMerchantDialog.vue"

const authStore = useAuthStore ()
const baseStore = useBaseStore ()
const merchantStore = useMerchantStore ()
const isEditDialogVisible = ref (false)

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const usersData = ref ([])
const editData = ref ({})

const updateUsers = () => {
  merchantStore.getMerchantFees ({}).then (
    response => {
      if (response.error) {
        snackbar.value = {
          enabled: true,
          type: 'error',
          message: response.error,
        }

        return
      }
      usersData.value = response.data
    },
  ).catch (
    error => {
      console.log ({ error })
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: error,
      }
    },
  )
}


onMounted (
  () => {
    updateUsers ()
  },
)

const editUser = user => {
  isEditDialogVisible.value = true
  editData.value = structuredClone (toRaw (user))
}
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
    <VRow>
      <VCol cols="12">
        <VCard>
          <VCardTitle class="mt-2 ms-2">
            <VAvatar
              size="50"
              variant="text"
              color="primary"
              icon="tabler-coin"
            />
            {{ $t ('tabs.manage_merchants') }}
            <VBtn
              class="float-end"
              icon="tabler-refresh"
              size="small"
              @click="updateUsers"
            />
          </VCardTitle>
          <VCol cols="12">
            <VCard>
              <VCardText>
                <VList>
                  <VListItem
                    v-for="item in usersData"
                    :key="item.merchant_id"
                    class="px-4 py-2"
                  >
                    <template #prepend>
                      <VIcon
                        icon="tabler-user"
                        class="me-3"
                      />
                    </template>

                    <VListItemTitle>
                      <span class="font-weight-bold">@{{ item.username }}</span>
                      <VTooltip
                        location="end"
                      >
                        <template #activator="{ props }">
                          <VBtn
                            v-bind="props"
                            size="xs"
                            class="ma-1 pa-1"
                            color="warning"
                            icon="tabler-pencil"
                            @click="editUser (item)"
                          />
                        </template>
                        <span>
                          Edit User
                        </span>
                      </VTooltip>
                    </VListItemTitle>
                  </VListItem>
                </VList>
              </VCardText>
            </VCard>
          </VCol>
        </VCard>
      </VCol>
    </VRow>
    <EditMerchantDialog
      v-model:is-dialog-visible="isEditDialogVisible"
      :data="editData"
      @update="updateUsers"
    />
  </div>
</template>

