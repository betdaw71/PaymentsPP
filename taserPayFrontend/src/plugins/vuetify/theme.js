import { resolveVuetifyTheme } from '@core/utils/vuetify'
import { themeConfig } from '@themeConfig'
import { brandColors } from '@/design/tokens'

export const staticPrimaryColor = brandColors.primary

const semanticColors = {
  'on-primary': '#fff',
  'secondary': brandColors.secondary,
  'on-secondary': '#fff',
  'alternative': brandColors.accent,
  'success': brandColors.success,
  'on-success': '#fff',
  'info': brandColors.info,
  'on-info': '#fff',
  'warning': brandColors.warning,
  'on-warning': '#fff',
  'error': brandColors.error,
  'on-error': '#fff',
}

const lightSurface = {
  'background': brandColors.background,
  'on-background': brandColors.text,
  'surface': brandColors.surface,
  'on-surface': brandColors.text,
}

const darkSurface = {
  'background': brandColors.backgroundDark,
  'on-background': brandColors.textDark,
  'surface': brandColors.surfaceDark,
  'on-surface': brandColors.textDark,
}

const greyScale = {
  'grey-50': '#F8FAFC',
  'grey-100': '#F1F5F9',
  'grey-200': '#E2E8F0',
  'grey-300': '#CBD5E1',
  'grey-400': '#94A3B8',
  'grey-500': '#64748B',
  'grey-600': '#475569',
  'grey-700': '#334155',
  'grey-800': '#1E293B',
  'grey-900': '#0F172A',
}

const themeVariables = {
  'code-color': brandColors.primary,
  'overlay-scrim-background': '#0F172A',
  'tooltip-background': '#334155',
  'overlay-scrim-opacity': 0.45,
  'hover-opacity': 0.04,
  'focus-opacity': 0.1,
  'selected-opacity': 0.06,
  'activated-opacity': 0.12,
  'pressed-opacity': 0.1,
  'dragged-opacity': 0.08,
  'disabled-opacity': 0.38,
  'border-color': brandColors.text,
  'border-opacity': 0.12,
  'high-emphasis-opacity': 0.87,
  'medium-emphasis-opacity': 0.6,
  'switch-opacity': 0.2,
  'switch-disabled-track-opacity': 0.3,
  'switch-disabled-thumb-opacity': 0.4,
  'switch-checked-disabled-opacity': 0.3,
  'shadow-key-umbra-color': '#0F172A',
}

const theme = {
  defaultTheme: resolveVuetifyTheme(),
  themes: {
    light: {
      dark: false,
      colors: {
        'primary': localStorage.getItem(`${themeConfig.app.title}-lightThemePrimaryColor`) || staticPrimaryColor,
        ...semanticColors,
        ...lightSurface,
        ...greyScale,
        'perfect-scrollbar-thumb': brandColors.border,
        'skin-bordered-background': brandColors.surface,
        'skin-bordered-surface': brandColors.surface,
      },
      variables: themeVariables,
    },
    dark: {
      dark: true,
      colors: {
        'primary': localStorage.getItem(`${themeConfig.app.title}-darkThemePrimaryColor`) || staticPrimaryColor,
        ...semanticColors,
        ...darkSurface,
        'grey-50': '#131A2B',
        'grey-100': '#151D2E',
        'grey-200': '#1E293B',
        'grey-300': '#334155',
        'grey-400': '#475569',
        'grey-500': '#64748B',
        'grey-600': '#94A3B8',
        'grey-700': '#CBD5E1',
        'grey-800': '#E2E8F0',
        'grey-900': '#F8FAFC',
        'perfect-scrollbar-thumb': '#334155',
        'skin-bordered-background': brandColors.surfaceDark,
        'skin-bordered-surface': brandColors.surfaceDark,
      },
      variables: {
        ...themeVariables,
        'border-color': brandColors.textDark,
        'overlay-scrim-opacity': 0.55,
      },
    },
    custom: {
      dark: false,
      colors: {
        'primary': localStorage.getItem(`${themeConfig.app.title}-lightThemePrimaryColor`) || staticPrimaryColor,
        ...semanticColors,
        ...lightSurface,
        ...greyScale,
        'perfect-scrollbar-thumb': brandColors.border,
        'skin-bordered-background': brandColors.surface,
        'skin-bordered-surface': brandColors.surface,
      },
      variables: themeVariables,
    },
  },
}

export default theme
