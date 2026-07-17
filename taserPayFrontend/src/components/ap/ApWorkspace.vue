<script setup>
defineProps({
  flat: {
    type: Boolean,
    default: false,
  },
  embedded: {
    type: Boolean,
    default: false,
  },
  noPadding: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <component
    :is="embedded ? 'div' : 'VCard'"
    class="ap-workspace"
    :class="{ 'ap-workspace--embedded': embedded }"
    :flat="embedded || flat"
  >
    <div
      v-if="$slots.header || $slots.actions"
      class="ap-workspace__header"
    >
      <div class="flex-grow-1">
        <slot name="header" />
      </div>
      <div
        v-if="$slots.actions"
        class="ap-page-header__actions"
      >
        <slot name="actions" />
      </div>
    </div>

    <div
      class="ap-workspace__body"
      :class="{ 'pa-0': noPadding }"
    >
      <slot />
    </div>

    <div
      v-if="$slots.footer"
      class="ap-workspace__footer"
    >
      <slot name="footer" />
    </div>
  </component>
</template>
