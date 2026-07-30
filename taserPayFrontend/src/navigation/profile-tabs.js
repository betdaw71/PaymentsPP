import { UI_ICONS } from '@/constants/ui-icons'

export function getProfileTabs (authStore) {
  const mainInfo = { key: 'main_info', title: 'tabs.main_info', icon: UI_ICONS.mainInfo, section: 'settings' }
  const team = { key: 'team', title: 'tabs.team', icon: UI_ICONS.team, section: 'account' }
  const balance = { key: 'balance', title: 'tabs.balance', icon: UI_ICONS.wallet, section: 'account' }
  const transactions = { key: 'transactions', title: 'tabs.transactions', icon: UI_ICONS.transactions, section: 'account' }
  const withdrawals = { key: 'withdrawals', title: 'tabs.withdrawals', icon: UI_ICONS.withdrawals, section: 'account' }
  const tradersBalance = { key: 'traders_balance', title: 'tabs.traders_balance', icon: UI_ICONS.tradersBalance, section: 'account' }
  const merchantsBalance = { key: 'merchants_balance', title: 'tabs.merchants_balance', icon: UI_ICONS.merchantsBalance, section: 'account' }
  const merchantsApi = { key: 'merchants_api', title: 'tabs.merchants_api', icon: UI_ICONS.api, section: 'settings' }
  const dashboard = { key: 'dashboard', title: 'tabs.dashboard', icon: UI_ICONS.dashboard, section: 'account' }

  if (authStore.is_senior_trader())
    return [mainInfo, team, balance, transactions, withdrawals]

  if (authStore.is_trader())
    return [mainInfo, team, balance, transactions]

  if (authStore.is_merchant_assist())
    return [mainInfo, balance, transactions]

  if (authStore.is_team_lead()) {
    const tabs = [mainInfo, balance, transactions, withdrawals]
    if (authStore.userData?.has_merchant_agent)
      tabs.splice(2, 0, { key: 'agent_merchants', title: 'tabs.agent_merchants', icon: UI_ICONS.merchantsBalance, section: 'account' })
    return tabs
  }

  if (authStore.is_merchant())
    return [mainInfo, balance, transactions, withdrawals, merchantsApi]

  if (authStore.is_head_of_support())
    return [dashboard, mainInfo, team, transactions, tradersBalance, merchantsBalance, withdrawals]

  if (authStore.is_support())
    return [mainInfo, team, transactions, tradersBalance, withdrawals]

  return [mainInfo, team, balance, transactions]
}

/** Sidebar-only: high-frequency items + profile entry; rest stays on profile page */
const SIDEBAR_TAB_KEYS = new Set(['dashboard', 'balance', 'transactions', 'withdrawals'])

export function profileTabToNavItem (tab) {
  return {
    title: tab.title,
    icon: { icon: tab.icon },
    to: {
      name: 'user',
      query: { tab: tab.key },
    },
    navSection: tab.section === 'settings' ? 'footer' : 'primary',
  }
}

export function getProfileNavItems (authStore) {
  const tabs = getProfileTabs(authStore)
  const items = tabs
    .filter(tab => SIDEBAR_TAB_KEYS.has(tab.key))
    .map(profileTabToNavItem)

  // Profile entry lives in header menu — avoid duplicate user icon in sidebar.

  if (authStore.is_head_of_support()) {
    items.push(
      {
        title: 'creation_studio',
        icon: { icon: UI_ICONS.creation },
        to: { name: 'user-add' },
        navSection: 'footer',
      },
      {
        title: 'management',
        icon: { icon: UI_ICONS.management },
        to: { name: 'user-manage' },
        navSection: 'footer',
      },
    )
  }

  return items
}
