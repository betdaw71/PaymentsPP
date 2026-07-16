<script setup>
defineProps({
  dense: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <div
    class="ap-filter-bar"
    :class="{ 'py-2': dense }"
  >
    <slot />
  </div>
</template>
