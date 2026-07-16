<script setup>
const props = defineProps({
  title: {
    type: String,
    default: '',
  },
  collapsible: {
    type: Boolean,
    default: true,
  },
  defaultOpen: {
    type: Boolean,
    default: true,
  },
})

const { t } = useI18n ()
const isOpen = ref (props.defaultOpen)

const toggle = () => {
  if (props.collapsible) {
    isOpen.value = !isOpen.value
  }
}
</script>

<template>
  <div
    class="ap-filter-panel"
    :class="{ 'ap-filter-panel--open': isOpen }"
  >
    <button
      type="button"
      class="ap-filter-panel__header"
      @click="toggle"
    >
      <div class="ap-filter-panel__header-left">
        <VIcon
          icon="tabler-adjustments-horizontal"
          size="20"
          class="ap-filter-panel__icon"
        />
        <span class="ap-filter-panel__title">
          {{ title || t('filters') }}
        </span>
      </div>
      <VIcon
        v-if="collapsible"
        :icon="isOpen ? 'tabler-chevron-up' : 'tabler-chevron-down'"
        size="18"
        class="ap-filter-panel__chevron"
      />
    </button>

    <VExpandTransition>
      <div
        v-show="isOpen"
        class="ap-filter-panel__body"
      >
        <slot />
      </div>
    </VExpandTransition>

    <div
      v-if="$slots.actions"
      class="ap-filter-panel__actions"
    >
      <slot name="actions" />
    </div>
  </div>
</template>
