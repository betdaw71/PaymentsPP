<script setup>
import { useAuthStore } from "@/stores/useAuthStore"
import { resolveRole } from '@/@core/utils/formatters'
import EventBus from "@/services/EventBus"

const authStore = useAuthStore ()
const router = useRouter ()

const profileRoute = computed(() => {
  if (authStore.is_head_of_support()) {
    return { name: 'user', query: { tab: 'dashboard' } }
  }

  return { name: 'user', query: { tab: 'main_info' } }
})

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
    <VBtn
      class="cursor-pointer text-lowercase"
      color="primary"
      variant="tonal"
      rounded="0"
      append-icon="tabler-user"
    >
      {{ authStore.userData.email }}

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

          <!-- 👉 Profile -->
          <VListItem :to="profileRoute">
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
