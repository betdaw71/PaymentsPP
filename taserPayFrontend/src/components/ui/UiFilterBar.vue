<script setup>
defineOptions({ name: 'UiFilterBar' })

const { t } = useI18n()

const props = defineProps({
  activeCount: {
    type: Number,
    default: 0,
  },
  loading: Boolean,
  applyLabel: {
    type: String,
    default: undefined,
  },
  resetLabel: {
    type: String,
    default: undefined,
  },
})

const emit = defineEmits(['apply', 'reset'])

const resolvedApplyLabel = computed(() => props.applyLabel ?? t('filter_apply'))
const resolvedResetLabel = computed(() => props.resetLabel ?? t('filter_reset'))
</script>

<template>
  <div class="ui-filter-bar">
    <div class="ui-filter-bar__meta">
      <VIcon
        icon="lucide:sliders-horizontal"
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
      {{ resolvedResetLabel }}
    </UiButton>
    <UiButton
      variant="primary"
      size="small"
      :loading="loading"
      @click="emit('apply')"
    >
      {{ resolvedApplyLabel }}
    </UiButton>
  </div>
</template>
