<script setup>
defineOptions({ name: 'UiSelect', inheritAttrs: false })

const props = defineProps({
  modelValue: {
    default: undefined,
  },
  label: String,
  items: {
    type: Array,
    default: () => [],
  },
  density: {
    type: String,
    default: 'compact',
  },
})

const emit = defineEmits(['update:modelValue'])

const elementId = computed(() => {
  const id = useAttrs().id || props.label
  return id ? `ui-select-${String(id).replace(/\s+/g, '-').toLowerCase()}` : undefined
})
</script>

<template>
  <div class="ui-field flex-grow-1">
    <VLabel
      v-if="label"
      :for="elementId"
      class="mb-1 text-body-2 text-high-emphasis"
      :text="label"
    />
    <VSelect
      :id="elementId"
      :model-value="modelValue"
      :items="items"
      :density="density"
      variant="outlined"
      color="primary"
      hide-details="auto"
      v-bind="$attrs"
      @update:model-value="emit('update:modelValue', $event)"
    >
      <template
        v-for="(_, name) in $slots"
        #[name]="slotProps"
      >
        <slot
          :name="name"
          v-bind="slotProps || {}"
        />
      </template>
    </VSelect>
  </div>
</template>
