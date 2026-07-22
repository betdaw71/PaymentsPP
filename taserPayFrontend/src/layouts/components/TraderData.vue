<script setup>
import { useAuthStore } from "@/stores/useAuthStore"

const authStore = useAuthStore()
</script>

<template>
  <div class="ap-header-balance d-none d-md-flex">
    <div class="ap-surface-chip ap-surface-chip--primary">
      <span class="ap-surface-chip__label">{{ $t('balance') }}</span>
      <span class="ap-surface-chip__value">{{ authStore.userData.current_balance }} USD</span>
    </div>
    <div class="ap-surface-chip ap-surface-chip--frozen">
      <span class="ap-surface-chip__label">{{ $t('hold') }}</span>
      <span class="ap-surface-chip__value">{{ authStore.userData.hold }} USD</span>
    </div>
  </div>
</template>
