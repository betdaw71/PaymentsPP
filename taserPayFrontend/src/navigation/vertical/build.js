import { getOperationsNavItems } from '@/navigation/vertical/index.js'
import { getProfileNavItems } from '@/navigation/profile-tabs.js'

function canSeeNavItem (navItem, authStore) {
  if (!navItem.role)
    return true

  if (Number.isInteger(navItem.role))
    return authStore.userData.role >= navItem.role

  if (Array.isArray(navItem.role))
    return navItem.role.includes(authStore.userData.role)

  return true
}

export function buildVerticalNavItems (authStore) {
  if (!authStore.userData?.role)
    return []

  const operations = getOperationsNavItems().filter(item => canSeeNavItem(item, authStore))
  const profileItems = getProfileNavItems(authStore)
  const accountPrimary = profileItems.filter(item => item.navSection !== 'footer')
  const accountFooter = profileItems.filter(item => item.navSection === 'footer')

  const items = [
    ...operations,
    { heading: 'nav_section_account' },
    ...accountPrimary,
  ]

  if (accountFooter.length) {
    items.push({ heading: 'nav_section_settings', navSection: 'footer' })
    items.push(...accountFooter)
  }

  return items
}
