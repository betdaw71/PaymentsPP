<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { resolveRole } from '@/@core/utils/formatters'
import EventBus from "@/services/EventBus"

const authStore = useAuthStore()

const displayEmail = computed(() => (authStore.userData.email || '').trim())
const displayUsername = computed(() => (authStore.userData.username || '').trim())
const showUsername = computed(() => {
  const username = displayUsername.value
  if (!username)
    return false

  const email = displayEmail.value
  if (!email)
    return true

  return username.toLowerCase() !== email.toLowerCase()
    && !email.toLowerCase().startsWith(`${username.toLowerCase()}@`)
})

const logout = () => {
  EventBus.dispatch("logout")
}
</script>

<template>
  <VMenu
    location="bottom end"
    offset="10px"
    width="280"
    style="z-index: 2002 !important;"
  >
    <template #activator="{ props: menuProps }">
      <button
        v-bind="menuProps"
        type="button"
        class="ap-profile-trigger"
        :aria-label="displayEmail || displayUsername || $t('user.profile.title')"
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

        <span
          v-if="displayEmail || showUsername"
          class="ap-profile-trigger__text d-none d-md-flex"
        >
          <span
            v-if="displayEmail"
            class="ap-profile-trigger__email"
          >{{ displayEmail }}</span>
          <span
            v-if="showUsername"
            class="ap-profile-trigger__username"
          >{{ displayUsername }}</span>
        </span>

        <VIcon
          icon="lucide:chevron-down"
          size="14"
          class="text-medium-emphasis flex-shrink-0"
        />
      </button>
    </template>

    <VList density="compact">
      <VListItem class="py-3">
        <template #prepend>
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
        </template>
        <VListItemTitle class="text-body-2 font-weight-medium text-truncate">
          {{ displayEmail || displayUsername }}
        </VListItemTitle>
        <VListItemSubtitle
          v-if="showUsername && displayEmail"
          class="text-truncate"
        >
          {{ displayUsername }}
        </VListItemSubtitle>
        <VListItemSubtitle class="mt-1">
          <VChip
            label
            v-bind="resolveRole(authStore.userData.role).chip"
            size="x-small"
          >
            {{ resolveRole(authStore.userData.role).status }}
          </VChip>
        </VListItemSubtitle>
      </VListItem>

      <VDivider class="my-1" />

      <VListItem :to="{ name: 'user', query: { tab: 'main_info' } }">
        <template #prepend>
          <VIcon
            class="me-2"
            icon="lucide:id-card"
            size="20"
          />
        </template>
        <VListItemTitle>{{ $t('user.profile.title') }}</VListItemTitle>
      </VListItem>

      <VListItem
        v-if="authStore.is_head_of_support()"
        :to="{ name: 'user-add'}"
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
        :to="{ name: 'user-manage'}"
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

      <VDivider class="my-1" />

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
</template>
