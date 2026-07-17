<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { resolveRole } from '@/@core/utils/formatters'
import EventBus from "@/services/EventBus"

const authStore = useAuthStore ()

const logout = () => {
  EventBus.dispatch("logout")
}
</script>

<template>
  <VMenu
    open-on-click
    width="280"
    location="bottom end"
    offset="8"
  >
    <template #activator="{ props: menuProps }">
      <button
        type="button"
        class="ap-profile-trigger"
        v-bind="menuProps"
      >
        <VBadge
          dot
          location="bottom right"
          offset-x="2"
          offset-y="2"
          bordered
          color="success"
        >
          <VAvatar
            color="primary"
            variant="tonal"
            size="36"
          >
            <VIcon
              icon="tabler-user"
              size="20"
            />
          </VAvatar>
        </VBadge>
        <span class="ap-profile-trigger__email d-none d-lg-inline">{{ authStore.userData.email }}</span>
        <VIcon
          icon="tabler-chevron-down"
          size="16"
          class="d-none d-lg-inline"
        />
      </button>
    </template>

    <VList density="compact">
      <VListItem class="py-3">
        <VListItemTitle class="font-weight-semibold text-wrap">
          {{ authStore.userData.email }}
        </VListItemTitle>
        <VListItemSubtitle class="mt-1">
          <VChip
            label
            v-bind="resolveRole(authStore.userData.role).chip"
            size="small"
          >
            {{ resolveRole(authStore.userData.role).status }}
          </VChip>
        </VListItemSubtitle>
      </VListItem>

      <VDivider />

      <VListItem
        class="text-error"
        @click="logout"
      >
        <template #prepend>
          <VIcon
            icon="tabler-logout"
            size="20"
          />
        </template>
        <VListItemTitle>{{ $t('user.logout.title') }}</VListItemTitle>
      </VListItem>
    </VList>
  </VMenu>
</template>
