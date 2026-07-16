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
  <div class="ap-kpi-card">
    <div class="ap-kpi-card__label">
      {{ label }}
    </div>
    <div
      v-if="value || $slots.default"
      class="ap-kpi-card__value"
    >
      <slot>{{ value }}</slot>
    </div>
    <div
      v-if="hint || $slots.hint"
      class="ap-kpi-card__hint"
    >
      <slot name="hint">
        {{ hint }}
      </slot>
    </div>
  </div>
</template>
