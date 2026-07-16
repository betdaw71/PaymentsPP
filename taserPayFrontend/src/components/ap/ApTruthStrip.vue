<script setup>
defineProps({
  items: {
    type: Array,
    default: () => [],
  },
})

const toneClass = tone => {
  if (!tone || tone === 'secondary') {
    return ''
  }

  return `ap-truth-strip__value--${tone}`
}
</script>

<template>
  <div class="ap-truth-strip">
    <div
      v-for="(item, index) in items"
      :key="`${item.label}-${index}`"
      class="ap-truth-strip__item"
      :class="{ 'ap-truth-strip__item--alert': item.alert }"
    >
      <div class="ap-truth-strip__label">
        {{ item.label }}
      </div>
      <div
        class="ap-truth-strip__value"
        :class="toneClass(item.tone)"
      >
        <VIcon
          v-if="item.icon"
          :icon="item.icon"
          size="16"
          class="me-1"
        />
        {{ item.value }}
      </div>
      <div
        v-if="item.hint"
        class="ap-truth-strip__hint"
      >
        {{ item.hint }}
      </div>
    </div>
  </div>
</template>
