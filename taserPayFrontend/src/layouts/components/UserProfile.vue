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
  <VBtn
    variant="text"
    class="ap-profile-menu"
    rounded="lg"
  >
    <VBadge
      dot
      location="bottom end"
      offset-x="2"
      offset-y="2"
      bordered
      color="success"
    >
      <VAvatar
        color="primary"
        variant="tonal"
        size="32"
      >
        <VIcon
          icon="lucide:user"
          size="16"
        />
      </VAvatar>
    </VBadge>

    <span class="ap-profile-menu__email d-none d-lg-inline ms-2">
      {{ authStore.userData.email }}
    </span>

    <VIcon
      icon="lucide:chevron-down"
      size="14"
      class="d-none d-lg-inline ms-1 text-medium-emphasis"
    />

    <VMenu
      open-on-hover
      activator="parent"
      width="300"
      location="bottom end"
      offset="10px"
      style="z-index: 2002 !important;"
    >
      <VList>
        <VListItem>
          <template #prepend>
            <VListItemAction start>
              <VBadge
                dot
                location="bottom end"
                offset-x="2"
                offset-y="2"
                color="success"
                bordered
              >
                <VAvatar
                  color="primary"
                  variant="tonal"
                  size="36"
                >
                  <VIcon
                    icon="lucide:user"
                    size="18"
                  />
                </VAvatar>
              </VBadge>
            </VListItemAction>
          </template>

          <VListItemTitle class="font-weight-semibold text-wrap">
            {{ authStore.userData.email }}
          </VListItemTitle>
          <VListItemSubtitle>
            <VChip
              label
              v-bind="resolveRole(authStore.userData.role).chip"
              size="small"
            >
              {{ resolveRole(authStore.userData.role).status }}
            </VChip>
          </VListItemSubtitle>
        </VListItem>

        <VDivider class="my-2" />

        <VListItem
          v-if="authStore.is_head_of_support()"
          :to="{ name: 'user-add' }"
        >
          <template #prepend>
            <VIcon
              class="me-2"
              icon="lucide:shapes"
              size="20"
            />
          </template>
          <VListItemTitle>{{ $t('creation_studio') }}</VListItemTitle>
        </VListItem>

        <VListItem
          v-if="authStore.is_head_of_support()"
          :to="{ name: 'user-manage' }"
        >
          <template #prepend>
            <VIcon
              class="me-2"
              icon="lucide:list-todo"
              size="20"
            />
          </template>
          <VListItemTitle>{{ $t('management') }}</VListItemTitle>
        </VListItem>

        <VListItem
          link
          @click="logout"
        >
          <template #prepend>
            <VIcon
              class="me-2"
              icon="lucide:log-out"
              size="20"
            />
          </template>
          <VListItemTitle>{{ $t('user.logout.title') }}</VListItemTitle>
        </VListItem>
      </VList>
    </VMenu>
  </VBtn>
</template>
