<script setup>
defineOptions({ name: 'UiWorkspace' })

defineProps({
  noPadding: {
    type: Boolean,
    default: true,
  },
})
</script>

<template>
  <section class="ui-workspace">
    <header
      v-if="$slots.header || $slots.actions"
      class="ui-workspace__header"
    >
      <div class="ui-workspace__header-main">
        <slot name="header" />
      </div>
      <div
        v-if="$slots.actions"
        class="ui-workspace__header-actions"
      >
        <slot name="actions" />
      </div>
    </header>

    <div
      class="ui-workspace__body"
      :class="{ 'ui-workspace__body--padded': !noPadding }"
    >
      <slot />
    </div>

    <footer
      v-if="$slots.footer"
      class="ui-workspace__footer"
    >
      <slot name="footer" />
    </footer>
  </section>
</template>
