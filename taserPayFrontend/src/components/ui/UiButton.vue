<script setup>
/**
 * Telegram (flat blue) + Shopify (bordered secondary) + Grafana (accent orange)
 * variant: default | primary | accent | active | ghost | danger
 */
defineOptions({ name: 'UiButton', inheritAttrs: false })

const props = defineProps({
  variant: {
    type: String,
    default: 'default',
    validator: v => ['default', 'primary', 'accent', 'active', 'ghost', 'danger'].includes(v),
  },
  size: {
    type: String,
    default: 'default',
  },
  loading: Boolean,
  disabled: Boolean,
  block: Boolean,
  icon: Boolean,
})

const vBtnBase = computed(() => ({
  variant: 'flat',
  color: undefined,
  elevation: 0,
}))
</script>

<template>
  <VBtn
    v-bind="{
      ...$attrs,
      ...vBtnBase,
      size,
      loading,
      disabled,
      block,
      icon,
    }"
    :class="['ui-btn', `ui-btn--${variant}`]"
  >
    <slot />
  </VBtn>
</template>
