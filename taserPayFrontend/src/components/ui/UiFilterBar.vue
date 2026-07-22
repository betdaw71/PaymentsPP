<script setup>
defineOptions({ name: 'UiFilterBar' })

defineProps({
  activeCount: {
    type: Number,
    default: 0,
  },
  loading: Boolean,
  applyLabel: {
    type: String,
    default: 'Применить',
  },
  resetLabel: {
    type: String,
    default: 'Сбросить',
  },
})

const emit = defineEmits(['apply', 'reset'])
</script>

<template>
  <div class="ui-filter-bar">
    <div class="ui-filter-bar__meta">
      <VIcon
        icon="tabler-adjustments-horizontal"
        size="16"
      />
      <span>Активные</span>
      <span
        v-if="activeCount > 0"
        class="ui-filter-panel__badge"
      >
        {{ activeCount }}
      </span>
    </div>

    <slot />

    <VSpacer />

    <UiButton
      variant="ghost"
      size="small"
      :disabled="loading"
      @click="emit('reset')"
    >
      {{ resetLabel }}
    </UiButton>
    <UiButton
      variant="primary"
      size="small"
      :loading="loading"
      @click="emit('apply')"
    >
      {{ applyLabel }}
    </UiButton>
  </div>
</template>
