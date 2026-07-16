<script setup>
defineProps({
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <div class="ap-page-header">
    <div class="ap-page-header__title">
      {{ title }}
    </div>
    <div
      v-if="subtitle || $slots.subtitle"
      class="ap-page-header__subtitle"
    >
      <slot name="subtitle">
        {{ subtitle }}
      </slot>
    </div>
  </div>
</template>
