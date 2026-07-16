<script setup>
defineProps({
  label: {
    type: String,
    required: true,
  },
  value: {
    type: String,
    default: '',
  },
  hint: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <div class="ap-metric-card">
    <div class="ap-metric-card__label">
      {{ label }}
    </div>
    <div
      v-if="value || $slots.default"
      class="ap-metric-card__value"
    >
      <slot>{{ value }}</slot>
    </div>
    <div
      v-if="hint || $slots.hint"
      class="ap-metric-card__hint"
    >
      <slot name="hint">
        {{ hint }}
      </slot>
    </div>
  </div>
</template>
