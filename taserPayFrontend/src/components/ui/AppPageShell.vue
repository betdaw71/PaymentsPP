<script setup>
defineProps({
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    default: '',
  },
  icon: {
    type: String,
    default: '',
  },
  flat: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <VRow>
    <VCol cols="12">
      <VCard
        class="ap-page-shell"
        :flat="flat"
      >
        <div class="ap-page-shell__header">
          <div
            v-if="icon"
            class="ap-page-shell__icon"
          >
            <VIcon
              :icon="icon"
              size="22"
            />
          </div>
          <div>
            <div class="ap-page-shell__title">
              {{ title }}
            </div>
            <div
              v-if="subtitle"
              class="ap-page-shell__subtitle"
            >
              {{ subtitle }}
            </div>
          </div>
          <VSpacer />
          <slot name="actions" />
        </div>

        <div
          v-if="$slots.toolbar"
          class="ap-page-shell__toolbar"
        >
          <slot name="toolbar" />
        </div>

        <div class="ap-page-shell__body">
          <slot />
        </div>
      </VCard>
    </VCol>
  </VRow>
</template>
