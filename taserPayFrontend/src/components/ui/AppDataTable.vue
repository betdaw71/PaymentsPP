<script setup>
defineProps({
  dense: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <VTable
    class="text-no-wrap ap-data-table"
    :density="dense ? 'compact' : 'default'"
  >
    <slot />
  </VTable>
</template>
