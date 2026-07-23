<script setup>
defineOptions({ name: 'UiDataTable' })

defineProps({
  density: {
    type: String,
    default: 'compact',
  },
  loading: Boolean,
})
</script>

<template>
  <div
    class="ui-data-table"
    :class="{ 'ui-data-table--loading': loading }"
  >
    <VTable
      :density="density"
      class="ui-data-table__table text-no-wrap"
    >
      <slot />
    </VTable>
  </div>
</template>
