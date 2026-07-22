<script setup>
defineOptions({ name: 'UiRefreshControl' })

const props = defineProps({
  interval: {
    type: Number,
    default: 0,
  },
  progress: {
    type: Number,
    default: 0,
  },
  progressSeconds: {
    type: Number,
    default: 0,
  },
  items: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['refresh', 'update:interval'])

const intervalLabel = computed(() => {
  const match = props.items.find(item => item.value === props.interval)
  return match?.name ?? 'Off'
})

const selectInterval = value => {
  emit('update:interval', value)
}
</script>

<template>
  <div class="ui-refresh-control">
    <VProgressCircular
      v-if="interval > 0"
      :model-value="progress"
      class="ui-refresh-control__ring cursor-pointer"
      :size="36"
      :width="2"
      color="primary"
      @click="emit('refresh')"
    >
      <span class="ui-refresh-control__seconds">{{ progressSeconds }}s</span>
    </VProgressCircular>
    <UiButton
      v-else
      variant="ghost"
      size="small"
      icon
      :title="$t('refresh')"
      @click="emit('refresh')"
    >
      <VIcon
        icon="lucide:refresh-cw"
        size="18"
      />
    </UiButton>

    <VMenu
      location="bottom end"
      :close-on-content-click="true"
    >
      <template #activator="{ props: menuProps }">
        <UiButton
          v-bind="menuProps"
          variant="default"
          size="small"
          class="ui-refresh-control__interval"
        >
          {{ intervalLabel }}
          <VIcon
            icon="lucide:chevron-down"
            size="14"
            end
          />
        </UiButton>
      </template>
      <VList
        density="compact"
        min-width="120"
      >
        <VListItem
          v-for="item in items"
          :key="item.value"
          :active="item.value === interval"
          :title="item.name"
          @click="selectInterval(item.value)"
        />
      </VList>
    </VMenu>
  </div>
</template>
