<script setup>
defineOptions({ name: 'UiFilterSection' })

defineProps({
  title: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <div class="ui-filter-section">
    <div
      v-if="title"
      class="ui-filter-section__title"
    >
      {{ title }}
    </div>
    <slot />
  </div>
</template>
