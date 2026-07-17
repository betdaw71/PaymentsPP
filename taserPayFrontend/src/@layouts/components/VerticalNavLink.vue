<script setup>
import { useLayouts } from '@layouts'
import { config } from '@layouts/config'
import { can } from '@layouts/plugins/casl'
import { isNavLinkActive } from '@layouts/utils'

const props = defineProps({
  item: {
    type: null,
    required: true,
  },
})

const router = useRouter()
const { width: windowWidth } = useWindowSize()
const { isVerticalNavMini, dynamicI18nProps } = useLayouts()
const hideTitleAndBadge = isVerticalNavMini(windowWidth)

const isActive = computed(() => isNavLinkActive(props.item, router))

const navigate = () => {
  const linkTo = props.item.to
  if (!linkTo) {
    return
  }

  router.push(typeof linkTo === 'string' ? { name: linkTo } : linkTo)
}
</script>

<template>
  <li
    v-if="can(item.action, item.subject)"
    class="nav-link"
    :class="{ disabled: item.disable }"
  >
    <a
      href="#"
      class="ap-nav-link"
      :class="{ 'ap-nav-link--active': isActive }"
      @click.prevent="navigate"
    >
      <Component
        :is="config.app.iconRenderer || 'div'"
        v-bind="item.icon || config.verticalNav.defaultNavItemIconProps"
        class="nav-item-icon"
      />
      <TransitionGroup name="transition-slide-x">
        <Component
          :is="config.app.enableI18n ? 'i18n-t' : 'span'"
          v-show="!hideTitleAndBadge"
          key="title"
          class="nav-item-title"
          v-bind="dynamicI18nProps(item.title, 'span')"
        >
          {{ item.title }}
        </Component>

        <Component
          :is="config.app.enableI18n ? 'i18n-t' : 'span'"
          v-if="item.badgeContent"
          v-show="!hideTitleAndBadge"
          key="badge"
          class="nav-item-badge"
          :class="item.badgeClass"
          v-bind="dynamicI18nProps(item.badgeContent, 'span')"
        >
          {{ item.badgeContent }}
        </Component>
      </TransitionGroup>
    </a>
  </li>
</template>

<style lang="scss">
.layout-vertical-nav {
  .nav-link a,
  .nav-link .ap-nav-link {
    display: flex;
    align-items: center;
  }
}
</style>
