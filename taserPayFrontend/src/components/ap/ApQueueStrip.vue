<script setup>
defineProps({
  items: {
    type: Array,
    default: () => [],
  },
})
</script>

<template>
  <div class="ap-queue-strip">
    <div
      v-for="(item, index) in items"
      :key="`${item.label}-${index}`"
      class="ap-queue-strip__item"
      :class="{
        'ap-queue-strip__item--active': item.count > 0,
        [`ap-queue-strip__item--${item.tone || 'secondary'}`]: item.count > 0,
      }"
    >
      <span class="ap-queue-strip__count">{{ item.count }}</span>
      <span class="ap-queue-strip__label">{{ item.label }}</span>
    </div>
  </div>
</template>
