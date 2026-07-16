<script setup>
defineProps({
  label: {
    type: String,
    required: true,
  },
  color: {
    type: String,
    default: 'secondary',
  },
  icon: {
    type: String,
    default: '',
  },
  variant: {
    type: String,
    default: 'tonal',
  },
  size: {
    type: String,
    default: 'small',
  },
})
</script>

<template>
  <VChip
    class="ap-status-badge"
    :color="color"
    :variant="variant"
    :size="size"
    label
  >
    <VIcon
      v-if="icon"
      :icon="icon"
      size="14"
      class="me-1"
    />
    {{ label }}
  </VChip>
</template>
