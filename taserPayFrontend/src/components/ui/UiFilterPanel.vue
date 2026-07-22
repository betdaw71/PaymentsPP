<script setup>
defineOptions({ name: 'UiFilterPanel' })

const props = defineProps({
  title: {
    type: String,
    default: 'Фильтры',
  },
  activeCount: {
    type: Number,
    default: 0,
  },
  expanded: {
    type: Boolean,
    default: true,
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

const emit = defineEmits(['apply', 'reset', 'update:expanded'])

const isOpen = computed({
  get: () => props.expanded,
  set: value => emit('update:expanded', value),
})

const toggle = () => {
  isOpen.value = !isOpen.value
}
</script>

<template>
  <section class="ui-filter-panel mb-4">
    <header
      class="ui-filter-panel__header"
      @click="toggle"
    >
      <div class="ui-filter-panel__title">
        <VIcon
          icon="tabler-filter"
          size="16"
          color="var(--ui-text-muted)"
        />
        <span>{{ title }}</span>
        <span
          v-if="activeCount > 0"
          class="ui-filter-panel__badge"
        >
          {{ activeCount }}
        </span>
      </div>
      <VBtn
        variant="text"
        size="x-small"
        icon
        @click.stop="toggle"
      >
        <VIcon
          :icon="isOpen ? 'tabler-chevron-up' : 'tabler-chevron-down'"
          size="18"
        />
      </VBtn>
    </header>

    <VExpandTransition>
      <div v-show="isOpen">
        <div class="ui-filter-panel__body">
          <slot />
        </div>
        <footer class="ui-filter-panel__footer">
          <UiButton
            variant="default"
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
        </footer>
      </div>
    </VExpandTransition>
  </section>
</template>
