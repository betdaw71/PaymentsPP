<script setup>
defineProps({
  dense: {
    type: Boolean,
    default: false,
  },
  clickableRows: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <div class="ap-data-grid-wrapper overflow-x-auto">
    <VTable
      class="text-no-wrap ap-data-grid"
      :density="dense ? 'compact' : 'default'"
    >
      <slot />
    </VTable>
  </div>
</template>
