<script setup>
import { PerfectScrollbar } from 'vue3-perfect-scrollbar'
import { VNodeRenderer } from './VNodeRenderer'
import {
  injectionKeyIsVerticalNavHovered,
  useLayouts,
} from '@layouts'
import {
  VerticalNavGroup,
  VerticalNavLink,
  VerticalNavSectionTitle,
} from '@layouts/components'
import { config } from '@layouts/config'

const props = defineProps({
  tag: {
    type: [
      String,
      null,
    ],
    required: false,
    default: 'aside',
  },
  navItems: {
    type: null,
    required: true,
  },
  isOverlayNavActive: {
    type: Boolean,
    required: true,
  },
  toggleIsOverlayNavActive: {
    type: Function,
    required: true,
  },
})

const refNav = ref()
const { width: windowWidth } = useWindowSize()
const isHovered = useElementHover(refNav)

provide(injectionKeyIsVerticalNavHovered, isHovered)

const {
  isVerticalNavCollapsed: isCollapsed,
  isLessThanOverlayNavBreakpoint,
  isVerticalNavMini,
  isAppRtl,
} = useLayouts()

const hideTitleAndIcon = isVerticalNavMini(windowWidth, isHovered)

const resolveNavItemComponent = item => {
  if ('heading' in item)
    return VerticalNavSectionTitle
  if ('children' in item)
    return VerticalNavGroup

  return VerticalNavLink
}

const primaryNavItems = computed(() => props.navItems.filter(item => item.navSection !== 'footer'))
const footerNavItems = computed(() => props.navItems.filter(item => item.navSection === 'footer'))

const route = useRoute()

watch(() => route.name, () => {
  props.toggleIsOverlayNavActive(false)
})

const isVerticalNavScrolled = ref(false)
const updateIsVerticalNavScrolled = val => isVerticalNavScrolled.value = val

const handleNavScroll = evt => {
  isVerticalNavScrolled.value = evt.target.scrollTop > 0
}
</script>

<template>
  <Component
    :is="props.tag"
    ref="refNav"
    class="layout-vertical-nav"
    :class="[
      {
        'overlay-nav': isLessThanOverlayNavBreakpoint(windowWidth),
        'hovered': isHovered,
        'visible': isOverlayNavActive,
        'scrolled': isVerticalNavScrolled,
      },
    ]"
  >
    <!-- 👉 Header -->
    <div
      class="nav-header"
      :class="{ 'nav-header--collapsed': isCollapsed && !isLessThanOverlayNavBreakpoint(windowWidth) }"
    >
      <slot name="nav-header">
        <RouterLink
          v-if="!isCollapsed || isLessThanOverlayNavBreakpoint(windowWidth)"
          to="/"
          class="app-logo d-flex align-center gap-x-3 app-title-wrapper"
        >
          <VNodeRenderer :nodes="config.app.logo" />

          <Transition name="vertical-nav-app-title">
            <h1
              v-show="!hideTitleAndIcon"
              class="app-title font-weight-bold text-capitalize leading-normal text-xl"
            >
              {{ config.app.title }}
            </h1>
          </Transition>
        </RouterLink>
        <!-- 👉 Vertical nav actions -->
        <!-- Show toggle collapsible in >md and close button in <md -->
        <template v-if="!isLessThanOverlayNavBreakpoint(windowWidth)">
          <Component
            :is="config.app.iconRenderer || 'div'"
            class="header-action nav-toggle"
            v-bind="isCollapsed ? config.icons.verticalNavUnPinned : config.icons.verticalNavPinned"
            @click.stop="isCollapsed = !isCollapsed"
          />
        </template>
        <template v-else>
          <Component
            :is="config.app.iconRenderer || 'div'"
            class="header-action"
            v-bind="config.icons.close"
            @click="toggleIsOverlayNavActive(false)"
          />
        </template>
      </slot>
    </div>
    <slot name="before-nav-items">
      <div class="vertical-nav-items-shadow" />
    </slot>
    <slot
      name="nav-items"
      :update-is-vertical-nav-scrolled="updateIsVerticalNavScrolled"
    >
      <div class="nav-items-shell">
        <PerfectScrollbar
          :key="isAppRtl"
          tag="ul"
          class="nav-items nav-items--primary"
          :options="{ wheelPropagation: false }"
          @ps-scroll-y="handleNavScroll"
        >
          <Component
            :is="resolveNavItemComponent(item)"
            v-for="(item, index) in primaryNavItems"
            :key="index"
            :item="item"
          />
        </PerfectScrollbar>
        <ul
          v-if="footerNavItems.length"
          class="nav-items nav-items--footer"
        >
          <Component
            :is="resolveNavItemComponent(item)"
            v-for="(item, index) in footerNavItems"
            :key="`footer-${index}`"
            :item="item"
          />
        </ul>
      </div>
    </slot>
  </Component>
</template>

<style lang="scss">
@use "@configured-variables" as variables;
@use "@layouts/styles/mixins";

// 👉 Vertical Nav
.layout-vertical-nav {
  position: fixed;
  z-index: variables.$layout-vertical-nav-z-index;
  display: flex;
  flex-direction: column;
  block-size: 100%;
  inline-size: var(--layout-nav-effective-width, var(--ui-nav-width, #{variables.$layout-vertical-nav-width}));
  max-inline-size: var(--layout-nav-effective-width, var(--ui-nav-width, #{variables.$layout-vertical-nav-width}));
  inset-block-start: 0;
  inset-inline-start: 0;
  transition: transform 0.25s ease-in-out, inline-size 0.25s ease-in-out, max-inline-size 0.25s ease-in-out, box-shadow 0.25s ease-in-out;
  will-change: transform, inline-size;

  .nav-header {
    display: flex;
    align-items: center;
    gap: 8px;
    position: relative;
    z-index: 2;

    .header-action {
      cursor: pointer;
    }

    &--collapsed {
      justify-content: center;
    }
  }

  .app-title-wrapper {
    margin-inline-end: auto;
    min-width: 0;
  }

  .nav-toggle {
    position: relative;
    z-index: 3;
    flex-shrink: 0;
  }

  .nav-items-shell {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    min-block-size: 0;
  }

  .nav-items {
    &--primary {
      flex: 1 1 auto;
      min-block-size: 0;
    }

    &--footer {
      flex-shrink: 0;
      margin-block-start: auto;
      padding-block: 8px 12px;
      border-block-start: 1px solid var(--ui-border, rgba(var(--v-border-color), calc(var(--v-border-opacity) * 0.35)));
      list-style: none;
      margin-inline: 0;
      padding-inline: 0;
    }
  }

  .nav-item-title {
    overflow: hidden;
    margin-inline-end: auto;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  // 👉 Collapsed — keep icon rail width even when hovered (avoids overlap with content)
  .layout-vertical-nav-collapsed & {
    inline-size: var(--layout-nav-effective-width, var(--ui-nav-width-collapsed, #{variables.$layout-vertical-nav-collapsed-width})) !important;
    max-inline-size: var(--layout-nav-effective-width, var(--ui-nav-width-collapsed, #{variables.$layout-vertical-nav-collapsed-width})) !important;
  }

  // 👉 Overlay nav
  &.overlay-nav {
    &:not(.visible) {
      transform: translateX(-#{variables.$layout-vertical-nav-width});

      @include mixins.rtl {
        transform: translateX(variables.$layout-vertical-nav-width);
      }
    }
  }
}
</style>
