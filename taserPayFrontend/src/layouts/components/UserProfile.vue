<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { resolveRole } from '@/@core/utils/formatters'
import EventBus from "@/services/EventBus"

const authStore = useAuthStore ()
const router = useRouter ()

const displayName = computed(() => {
  return authStore.userData.username || authStore.userData.email || ''
})

const logout = () => {
  EventBus.dispatch("logout")
}
</script>

<template>
  <VBadge
    class="user-profile-badge"
    dot
    location="bottom right"
    offset-x="3"
    offset-y="3"
    bordered
    color="success"
  >
    <VBtn
      rounded
      class="cursor-pointer text-lowercase user-profile-btn"
      color="primary"
      variant="tonal"
      append-icon="tabler-user"
    >
      <span class="user-profile-label">{{ displayName }}</span>

      <!-- SECTION Menu -->
      <VMenu
        open-on-hover
        activator="parent"
        width="300"
        location="bottom end"
        offset="14px"
        style="z-index: 2002 !important;"
      >
        <VList>
          <!-- 👉 User Avatar & Name -->
          <VListItem>
            <template #prepend>
              <VListItemAction start>
                <VBadge
                  dot
                  location="bottom right"
                  offset-x="3"
                  offset-y="3"
                  color="success"
                  bordered
                >
                  <VAvatar
                    color="primary"
                    variant="tonal"
                  >
                    <VIcon
                      icon="tabler-user"
                    />
                  </VAvatar>
                </VBadge>
              </VListItemAction>
            </template>

            <VListItemTitle class="font-weight-semibold text-truncate">
              {{ displayName }}
            </VListItemTitle>
            <VListItemSubtitle>
              <div
                v-if="authStore.userData.email && authStore.userData.email !== displayName"
                class="text-truncate mb-1"
              >
                {{ authStore.userData.email }}
              </div>
              <VChip
                label
                v-bind="resolveRole(authStore.userData.role).chip"
                size="small"
              >
                {{ resolveRole (authStore.userData.role).status }}
              </VChip>
            </VListItemSubtitle>
          </VListItem>

          <VDivider class="my-2" />

          <!-- 👉 Profile -->
          <VListItem :to="{ name: 'user'}">
            <template #prepend>
              <VIcon
                class="me-2"
                icon="tabler-user"
                size="22"
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
                icon="tabler-geometry"
                size="22"
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
                icon="tabler-subtask"
                size="22"
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
                icon="tabler-logout"
                size="22"
              />
            </template>

            <VListItemTitle>{{ $t('user.logout.title') }}</VListItemTitle>
          </VListItem>
        </VList>
      </VMenu>
      <!-- !SECTION -->
    </VBtn>
  </VBadge>
</template>

<style scoped>
.user-profile-badge {
  display: block;
  max-width: min(42vw, 11rem);
  min-width: 0;
  flex: 0 1 auto;
}

.user-profile-badge :deep(.v-badge__wrapper) {
  max-width: 100%;
}

@media (min-width: 960px) {
  .user-profile-badge {
    max-width: 14rem;
  }
}

.user-profile-btn {
  max-width: 100%;
}

.user-profile-btn :deep(.v-btn__content) {
  min-width: 0;
  overflow: hidden;
}

.user-profile-label {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
