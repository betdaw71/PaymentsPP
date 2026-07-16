export default [
  { heading: 'nav.operations' },
  {
    title: 'tabs.orders_in',
    icon: { icon: 'tabler-arrow-down-left' },
    children: [
      {
        title: 'all',
        to: { name: 'orders-in-type', params: { type: 'all' } },
        icon: { icon: 'tabler-list' },
      },
      {
        title: 'active',
        to: { name: 'orders-in-type', params: { type: 'active' } },
        icon: { icon: 'tabler-progress' },
      },
      {
        title: 'success',
        to: { name: 'orders-in-type', params: { type: 'success' } },
        icon: { icon: 'tabler-check' },
      },
      {
        title: 'recalculation',
        to: { name: 'orders-in-type', params: { type: 'recalculation' } },
        icon: { icon: 'tabler-calculator' },
      },
      {
        title: 'declined',
        to: { name: 'orders-in-type', params: { type: 'declined' } },
        icon: { icon: 'tabler-x' },
      },
      {
        title: 'arbitrage',
        to: { name: 'orders-in-type', params: { type: 'arbitrage' } },
        icon: { icon: 'tabler-shield-lock' },
      },
    ],
    role: 1,
  },
  {
    title: 'tabs.orders_out',
    icon: { icon: 'tabler-arrow-up-right' },
    children: [
      {
        title: 'all',
        to: { name: 'orders-out-type', params: { type: 'all' } },
        icon: { icon: 'tabler-list' },
      },
      {
        title: 'active',
        to: { name: 'orders-out-type', params: { type: 'active' } },
        icon: { icon: 'tabler-progress' },
      },
      {
        title: 'success',
        to: { name: 'orders-out-type', params: { type: 'success' } },
        icon: { icon: 'tabler-check' },
      },
      {
        title: 'recalculation',
        to: { name: 'orders-out-type', params: { type: 'recalculation' } },
        icon: { icon: 'tabler-calculator' },
      },
      {
        title: 'declined',
        to: { name: 'orders-out-type', params: { type: 'declined' } },
        icon: { icon: 'tabler-x' },
      },
      {
        title: 'manual_check',
        to: { name: 'orders-out-type', params: { type: 'manual' } },
        icon: { icon: 'tabler-eye-check' },
      },
    ],
    role: 1,
  },
  {
    title: 'sms',
    to: { name: 'sms-sms' },
    icon: { icon: 'tabler-device-mobile-message' },
    role: [1, 2, 4, 5],
  },

  { heading: 'nav.assets' },
  {
    title: 'payment_details',
    to: { name: 'payment-details' },
    icon: { icon: 'tabler-credit-card' },
    role: [1, 2, 4, 5],
  },
  {
    title: 'tabs.balance',
    to: { name: 'user', query: { tab: 'balance' } },
    icon: { icon: 'tabler-wallet' },
    role: [1, 2, 3, 6, 7],
  },
  {
    title: 'tabs.traders_balance',
    to: { name: 'user', query: { tab: 'traders_balance' } },
    icon: { icon: 'tabler-coins' },
    role: [4, 5],
  },
  {
    title: 'tabs.merchants_balance',
    to: { name: 'user', query: { tab: 'merchants_balance' } },
    icon: { icon: 'tabler-building-bank' },
    role: 5,
  },

  { heading: 'nav.finance' },
  {
    title: 'tabs.transactions',
    to: { name: 'user', query: { tab: 'transactions' } },
    icon: { icon: 'tabler-arrows-exchange' },
    role: 1,
  },
  {
    title: 'tabs.withdrawals',
    to: { name: 'user', query: { tab: 'withdrawals' } },
    icon: { icon: 'tabler-cash-banknote' },
    role: [2, 3, 4, 5, 6, 7],
  },
  {
    title: 'tabs.merchants_api',
    to: { name: 'user', query: { tab: 'merchants_api' } },
    icon: { icon: 'tabler-api' },
    role: 3,
  },

  { heading: 'nav.people' },
  {
    title: 'tabs.team',
    to: { name: 'user', query: { tab: 'team' } },
    icon: { icon: 'tabler-users' },
    role: [1, 2, 4, 5],
  },
  {
    title: 'tabs.main_info',
    to: { name: 'user', query: { tab: 'main_info' } },
    icon: { icon: 'tabler-user-circle' },
    role: 1,
  },

  { heading: 'nav.analytics' },
  {
    title: 'tabs.dashboard',
    to: { name: 'user', query: { tab: 'dashboard' } },
    icon: { icon: 'tabler-chart-histogram' },
    role: 5,
  },

  { heading: 'nav.admin' },
  {
    title: 'tabs.manage_merchants',
    to: { name: 'user-manage' },
    icon: { icon: 'tabler-building-store' },
    role: 5,
  },
  {
    title: 'nav.add_user',
    to: { name: 'user-add' },
    icon: { icon: 'tabler-user-plus' },
    role: 5,
  },
]
