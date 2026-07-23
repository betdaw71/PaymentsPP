<template>
  <div class="h-100 d-flex align-center justify-space-between">
    <span class="d-flex align-center text-body-2">
      <span class="font-weight-semibold">&copy; {{ new Date().getFullYear() }}</span>
      <span class="mx-2 text-disabled">·</span>
      <span>{{ themeConfig.app.title }}</span>
    </span>
    <span
      class="text-body-2 text-medium-emphasis font-weight-medium"
      :title="buildCommit ? `build ${buildCommit}` : undefined"
    >
      {{ versionLabel }}
    </span>
  </div>
</template>

<script setup>
import { themeConfig } from '@themeConfig'
import { buildCommit, formatAppVersion } from '@/constants/appVersion'

const versionLabel = formatAppVersion({ includeCommit: !!buildCommit })
</script>
