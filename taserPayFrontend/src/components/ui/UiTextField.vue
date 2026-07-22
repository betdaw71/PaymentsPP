<script setup>
defineOptions({ name: 'UiTextField', inheritAttrs: false })

const props = defineProps({
  modelValue: {
    type: [String, Number],
    default: undefined,
  },
  label: String,
  hint: String,
  density: {
    type: String,
    default: 'compact',
  },
})

const emit = defineEmits(['update:modelValue'])

const elementId = computed(() => {
  const id = useAttrs().id || props.label
  return id ? `ui-field-${String(id).replace(/\s+/g, '-').toLowerCase()}` : undefined
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
    <VTextField
      :id="elementId"
      :model-value="modelValue"
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
    </VTextField>
    <div
      v-if="hint"
      class="text-caption text-medium-emphasis mt-1"
    >
      {{ hint }}
    </div>
  </div>
</template>
