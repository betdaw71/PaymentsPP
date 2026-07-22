<script setup>
defineOptions({ name: 'AccountListLayout' })

const props = defineProps({
  filterPanelExpanded: {
    type: Boolean,
    required: true,
  },
  rowsPerPage: {
    type: Number,
    required: true,
  },
  currentPage: {
    type: Number,
    required: true,
  },
  advancedFilterCount: {
    type: Number,
    default: 0,
  },
  activeFilterChips: {
    type: Array,
    default: () => [],
  },
  rowsPerPageOptions: {
    type: Array,
    required: true,
  },
  paginationData: {
    type: String,
    default: '',
  },
  totalPage: {
    type: Number,
    required: true,
  },
})

const emit = defineEmits([
  'update:filterPanelExpanded',
  'update:rowsPerPage',
  'update:currentPage',
  'search',
  'reset',
  'remove-chip',
  'clear-all',
  'refresh',
])

const toggleFilterPanel = () => {
  emit('update:filterPanelExpanded', !props.filterPanelExpanded)
}
</script>

<template>
  <div class="ui-account-list">
    <div class="ui-account-list__toolbar">
      <div class="ui-account-list__toolbar-actions">
        <slot name="toolbar-actions" />
        <UiButton
          variant="ghost"
          size="small"
          icon
          @click="emit('refresh')"
        >
          <VIcon
            icon="lucide:refresh-cw"
            size="16"
          />
        </UiButton>
      </div>
    </div>

    <div class="ui-orders-filter-zone">
      <div class="ui-orders-search">
        <slot name="search-fields" />
        <UiButton
          variant="default"
          size="small"
          @click="toggleFilterPanel"
        >
          <VIcon
            icon="lucide:filter"
            size="16"
            start
          />
          {{ $t('filters') }}
          <span
            v-if="advancedFilterCount > 0"
            class="ui-filter-panel__badge ms-1"
          >
            {{ advancedFilterCount }}
          </span>
        </UiButton>
        <UiButton
          variant="primary"
          size="small"
          @click="emit('search')"
        >
          <VIcon
            icon="lucide:search"
            size="16"
            start
          />
          {{ $t('search') }}
        </UiButton>
      </div>

      <UiFilterChips
        :chips="activeFilterChips"
        :clear-label="$t('clear_all_filters')"
        @remove="emit('remove-chip', $event)"
        @clear-all="emit('clear-all')"
      />

      <UiFilterPanel
        :expanded="filterPanelExpanded"
        :active-count="advancedFilterCount"
        :title="$t('advanced_filters')"
        embedded
        @update:expanded="emit('update:filterPanelExpanded', $event)"
        @apply="emit('search')"
        @reset="emit('reset')"
      >
        <slot name="filters" />
      </UiFilterPanel>
    </div>

    <slot name="table" />

    <div class="ui-orders-footer ui-account-list__footer">
      <span class="text-sm text-disabled">{{ paginationData }}</span>
      <div class="d-flex align-center gap-4">
        <div class="ui-orders-footer__rows">
          <VSelect
            :model-value="rowsPerPage"
            :items="rowsPerPageOptions"
            :label="$t('rows')"
            item-title="name"
            item-value="value"
            density="compact"
            hide-details
            scroll-strategy="close"
            color="primary"
            @update:model-value="emit('update:rowsPerPage', $event)"
          />
        </div>
        <VPagination
          :model-value="currentPage"
          size="small"
          :total-visible="5"
          :length="totalPage"
          @update:model-value="emit('update:currentPage', $event)"
        />
      </div>
    </div>
  </div>
</template>
