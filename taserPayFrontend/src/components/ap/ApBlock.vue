<script setup>
defineProps({
  title: {
    type: String,
    default: '',
  },
})
</script>

<template>
  <section class="ap-block">
    <header
      v-if="title || $slots.title"
      class="ap-block__header"
    >
      <slot name="title">
        <h3 class="ap-block__title">
          {{ title }}
        </h3>
      </slot>
      <div
        v-if="$slots.actions"
        class="ap-block__actions"
      >
        <slot name="actions" />
      </div>
    </header>
    <div class="ap-block__body">
      <slot />
    </div>
  </section>
</template>
