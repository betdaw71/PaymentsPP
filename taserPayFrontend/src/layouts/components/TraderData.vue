<script setup>
import { useAuthStore } from "@/stores/useAuthStore"

const authStore = useAuthStore ()
</script>

<template>
  <VBtn
    rounded
    class="d-none d-md-block cursor-pointer me-4"
    color="primary"
    variant="tonal"
  >
    <span
      class="font-weight-bold"
      style="color: rgba(var(--v-theme-on-background), var(--v-high-emphasis-opacity))"
    >{{ $t('balance') }}: {{ authStore.userData.current_balance }}&nbsp;USD</span>
  </VBtn>
</template>

<style scoped lang="scss">
</style>
