<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { resolveRole } from '@/@core/utils/formatters'
import EventBus from "@/services/EventBus"

const authStore = useAuthStore ()
const router = useRouter ()

const logout = () => {
  EventBus.dispatch("logout")
}
</script>

<template>
  <VBadge
    dot
    location="bottom right"
    offset-x="3"
    offset-y="3"
    bordered
    color="success"
  >
    <button
      type="button"
      class="ap-profile-trigger"
    >
      <VAvatar
        color="primary"
        variant="tonal"
        size="28"
      >
        <VIcon
          icon="lucide:user"
          size="16"
        />
      </VAvatar>
      <span class="ap-profile-trigger__email d-none d-lg-inline">{{ authStore.userData.email }}</span>
      <VIcon
        icon="lucide:chevron-down"
        size="14"
        class="d-none d-lg-inline text-medium-emphasis"
      />

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
                      icon="lucide:user"
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
                {{ resolveRole (authStore.userData.role).status }}
              </VChip>
            </VListItemSubtitle>
          </VListItem>

          <VDivider class="my-2" />

          <!-- Profile shortcut removed — account tabs live in the sidebar -->
          <VListItem
            v-if="authStore.is_head_of_support()"
            :to="{ name: 'user-add'}"
          >
            <template #prepend>
              <VIcon
                class="me-2"
                icon="lucide:shapes"
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
                icon="lucide:list-todo"
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
                icon="lucide:log-out"
                size="22"
              />
            </template>

            <VListItemTitle>{{ $t('user.logout.title') }}</VListItemTitle>
          </VListItem>
        </VList>
      </VMenu>
      <!-- !SECTION -->
    </button>
  </VBadge>
</template>
