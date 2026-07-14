<template>
  <div class="h-100 d-flex align-center justify-space-between">
    <VRow>
      <VCol
        cols="5"
      >
        <span class="d-flex align-center">
          <span class="text-body-1 font-weight-bold">
            &copy;
            {{ new Date ().getFullYear () }}</span>
          &nbsp;&nbsp;{{ themeConfig.app.title }}
        </span>
      </VCol>
      <VCol
        cols="7"
        class="align-content-center"
      >
        <span class="d-flex gap-x-4 text-primary d-none justify-center float-end">
          v{{ version }}
        </span>
      </VCol>
    </VRow>
  </div>
</template>

<script setup>
import { themeConfig } from '@themeConfig'

const version = import.meta.env.PACKAGE_VERSION
</script>
