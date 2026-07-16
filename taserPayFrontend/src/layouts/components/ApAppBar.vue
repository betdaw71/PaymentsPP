<script setup>
defineProps({
  showMenuToggle: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['toggleNav'])
</script>

<template>
  <div class="ap-app-bar d-flex h-100 align-center px-4 px-md-6">
    <IconBtn
      v-if="showMenuToggle"
      id="vertical-nav-toggle-btn"
      class="me-2"
      @click="$emit('toggleNav')"
    >
      <VIcon
        icon="tabler-menu-2"
        size="24"
      />
    </IconBtn>

    <slot name="leading" />

    <VSpacer />

    <div class="d-flex align-center gap-2">
      <slot />
    </div>
  </div>
</template>
