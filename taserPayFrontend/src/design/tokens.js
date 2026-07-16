/**
 * AvaPay design tokens — single source of truth for the rebrand.
 * Avoid Vuexy defaults (#7367F0, #28C76F, #00CFE8, bordered skin).
 */

export const brandColors = {
  primary: '#0B5FFF',
  primaryDark: '#0847C7',
  secondary: '#64748B',
  success: '#10B981',
  info: '#06B6D4',
  warning: '#F59E0B',
  error: '#EF4444',
  alternative: '#8B5CF6',

  surfaceLight: '#FFFFFF',
  backgroundLight: '#F8FAFC',
  textPrimaryLight: '#0F172A',
  textMutedLight: '#64748B',

  surfaceDark: '#151D2E',
  backgroundDark: '#0B1220',
  textPrimaryDark: '#E2E8F0',
  textMutedDark: '#94A3B8',
}

export const brandRadii = {
  sm: '6px',
  md: '10px',
  lg: '14px',
  xl: '20px',
}

export const brandShadows = {
  card: '0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04)',
  cardHover: '0 4px 12px rgba(15, 23, 42, 0.08)',
  nav: '0 2px 8px rgba(15, 23, 42, 0.06)',
}

export const brandSpacing = {
  pagePadding: '1.5rem',
  sectionGap: '1.25rem',
  cardPadding: '1.25rem',
}

export const chartPalette = [
  brandColors.primary,
  brandColors.success,
  brandColors.warning,
  brandColors.info,
  brandColors.alternative,
  brandColors.secondary,
]
