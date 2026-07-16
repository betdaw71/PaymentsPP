import { breakpointsVuetify } from '@vueuse/core'
import { VIcon } from 'vuetify/components'

// ❗ Logo SVG must be imported with ?raw suffix
import logo from '@images/logo.svg?raw'
import { defineThemeConfig } from '@core'
import { RouteTransitions, Skins } from '@core/enums'
import { AppContentLayoutNav, ContentWidth, FooterType, NavbarType } from '@layouts/enums'

export const { themeConfig, layoutConfig } = defineThemeConfig({
  app: {
    title: 'AvaPay',
    slogan: "&dash; Payment Solution &dash;",
    logo: h('div', { innerHTML: logo, style: 'line-height:0; color: rgb(var(--v-global-theme-primary));' }),
    contentWidth: ContentWidth.Fluid,
    contentLayoutNav: AppContentLayoutNav.Vertical,
    overlayNavFromBreakpoint: breakpointsVuetify.md + 16,
    enableI18n: true,
    theme: 'custom',
    isRtl: false,
    skin: Skins.Default,
    routeTransition: RouteTransitions.Fade,
    iconRenderer: VIcon,
  },
  navbar: {
    type: NavbarType.Sticky,
    navbarBlur: true,
  },
  footer: { type: FooterType.Sticky },
  verticalNav: {
    isVerticalNavCollapsed: false,
    defaultNavItemIconProps: { icon: 'tabler-point-filled', size: 6 },
    isVerticalNavSemiDark: false,
  },
  horizontalNav: {
    type: 'sticky',
    transition: 'slide-y-reverse-transition',
  },
  icons: {
    chevronDown: { icon: 'tabler-chevron-down' },
    chevronRight: { icon: 'tabler-chevron-right', size: 18 },
    close: { icon: 'tabler-x' },
    verticalNavPinned: { icon: 'tabler-pin-filled' },
    verticalNavUnPinned: { icon: 'tabler-pin' },
    sectionTitlePlaceholder: { icon: 'tabler-minus-vertical' },
  },
})
