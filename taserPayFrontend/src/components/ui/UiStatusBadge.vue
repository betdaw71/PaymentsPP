<script setup>
defineOptions({ name: 'UiStatusBadge' })

defineProps({
  color: {
    type: String,
    required: true,
  },
  icon: {
    type: String,
    default: undefined,
  },
  label: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <VChip
    size="small"
    :color="color"
    variant="flat"
    class="ui-status-badge"
    :prepend-icon="icon"
  >
    <slot>{{ label }}</slot>
  </VChip>
</template>
