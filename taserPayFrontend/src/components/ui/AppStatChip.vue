<script setup>
defineProps({
  label: {
    type: String,
    required: true,
  },
  value: {
    type: [String, Number],
    required: true,
  },
  color: {
    type: String,
    default: 'primary',
  },
  tooltip: {
    type: String,
    default: '',
  },
  prefix: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <VTooltip
    :disabled="!tooltip"
    location="bottom"
  >
    <template #activator="{ props: tooltipProps }">
      <VChip
        v-bind="tooltipProps"
        class="ap-stat-chip"
        :color="color"
        size="small"
        label
      >
        {{ prefix }}{{ value }}
      </VChip>
    </template>
    <span>{{ tooltip }}</span>
  </VTooltip>
</template>
