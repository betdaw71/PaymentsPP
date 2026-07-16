<script setup>
defineProps({
  title: {
    type: String,
    default: '',
  },
  bordered: {
    type: Boolean,
    default: true,
  },
})
</script>

<template>
  <div
    class="ap-section"
    :class="{ 'ap-section--bordered': bordered }"
  >
    <div
      v-if="title || $slots.title"
      class="ap-section__title"
    >
      <slot name="title">
        {{ title }}
      </slot>
    </div>
    <slot />
  </div>
</template>
