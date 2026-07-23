<script setup>
import NavBarI18n from '@core/components/I18n.vue'
import { useThemeConfig } from '@core/composable/useThemeConfig'

const { isAppRtl, theme } = useThemeConfig()

const i18nCompLanguages = [
  {
    label: 'English',
    i18nLang: 'en',
  },
  {
    label: 'Russian',
    i18nLang: 'ru',
  },
]

const handleLangChange = lang => {
  isAppRtl.value = lang === 'ar'
  localStorage.setItem ('lang', lang)
}

const isDarkTheme = computed(() => theme.value === 'dark')

const toggleTheme = () => {
  theme.value = isDarkTheme.value ? 'custom' : 'dark'
}
</script>

<template>
  <div class="d-flex align-center">
    <VBtn
      icon
      variant="text"
      color="default"
      size="small"
      class="me-1"
      @click="toggleTheme"
    >
      <VIcon
        size="22"
        :icon="isDarkTheme ? 'lucide:sun' : 'lucide:moon'"
      />
    </VBtn>

    <NavBarI18n
      :languages="i18nCompLanguages"
      @change="handleLangChange"
    />
  </div>
</template>
