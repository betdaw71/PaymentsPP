<script setup>
defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  compact: {
    type: Boolean,
    default: false,
  },
})

const toneClass = tone => {
  if (!tone || tone === 'secondary') {
    return ''
  }

  return `ap-truth-strip__item--${tone}`
}

const valueToneClass = tone => {
  if (!tone || tone === 'secondary') {
    return ''
  }

  return `ap-truth-strip__value--${tone}`
}
</script>

<template>
  <div
    class="ap-truth-strip"
    :class="{ 'ap-truth-strip--compact': compact }"
  >
    <div
      v-for="(item, index) in items"
      :key="`${item.label}-${index}`"
      class="ap-truth-strip__item"
      :class="[
        toneClass(item.tone),
        { 'ap-truth-strip__item--alert': item.alert },
      ]"
    >
      <div
        v-if="!compact"
        class="ap-truth-strip__label"
      >
        {{ item.label }}
      </div>
      <div
        class="ap-truth-strip__value"
        :class="valueToneClass(item.tone)"
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
        v-if="item.hint && !compact"
        class="ap-truth-strip__hint"
      >
        {{ item.hint }}
      </div>
    </div>
  </div>
</template>
