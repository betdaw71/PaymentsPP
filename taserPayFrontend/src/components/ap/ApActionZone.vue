<script setup>
defineProps({
  sticky: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <div
    class="ap-action-zone"
    :class="{ 'ap-action-zone--sticky': sticky }"
  >
    <div class="ap-action-zone__leading">
      <slot name="leading" />
    </div>
    <VSpacer />
    <div class="ap-action-zone__actions">
      <slot />
    </div>
  </div>
</template>
