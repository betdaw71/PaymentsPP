<script setup>
defineOptions({ name: 'UiFilterChips' })

defineProps({
  chips: {
    type: Array,
    default: () => [],
  },
  clearLabel: {
    type: String,
    default: 'Clear all',
  },
})

const emit = defineEmits(['remove', 'clear-all'])
</script>

<template>
  <div
    v-if="chips.length > 0"
    class="ui-filter-chips"
  >
    <span
      v-for="chip in chips"
      :key="chip.key"
      class="ui-chip ui-chip--removable"
      role="button"
      tabindex="0"
      @click="emit('remove', chip.key)"
      @keydown.enter="emit('remove', chip.key)"
    >
      {{ chip.label }}
      <VIcon
        icon="lucide:x"
        size="12"
      />
    </span>
    <button
      type="button"
      class="ui-filter-chips__clear"
      @click="emit('clear-all')"
    >
      {{ clearLabel }}
    </button>
  </div>
</template>
