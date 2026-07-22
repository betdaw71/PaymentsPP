import { UI_ICONS } from '@/constants/ui-icons'

const orderStatusChildren = type => [
  {
    title: 'all',
    to: { name: `orders-${type}-type`, params: { type: 'all' } },
    icon: { icon: UI_ICONS.all },
  },
  {
    title: 'active',
    to: { name: `orders-${type}-type`, params: { type: 'active' } },
    icon: { icon: UI_ICONS.active },
  },
  {
    title: 'success',
    to: { name: `orders-${type}-type`, params: { type: 'success' } },
    icon: { icon: UI_ICONS.success },
  },
  {
    title: 'recalculation',
    to: { name: `orders-${type}-type`, params: { type: 'recalculation' } },
    icon: { icon: UI_ICONS.recalculation },
  },
  {
    title: 'declined',
    to: { name: `orders-${type}-type`, params: { type: 'declined' } },
    icon: { icon: UI_ICONS.declined },
  },
]

export function getOperationsNavItems () {
  return [
    { heading: 'nav_section_operations' },
    {
      title: 'tabs.orders_in',
      icon: { icon: UI_ICONS.ordersIn },
      children: [
        ...orderStatusChildren('in'),
        {
          title: 'arbitrage',
          to: { name: 'orders-in-type', params: { type: 'arbitrage' } },
          icon: { icon: UI_ICONS.arbitrage },
        },
      ],
      role: 1,
    },
    {
      title: 'tabs.orders_out',
      icon: { icon: UI_ICONS.ordersOut },
      children: [
        ...orderStatusChildren('out'),
        {
          title: 'manual_check',
          to: { name: 'orders-out-type', params: { type: 'manual' } },
          icon: { icon: UI_ICONS.manualCheck },
        },
      ],
      role: 1,
    },
    {
      title: 'payment_details',
      to: { name: 'payment-details' },
      icon: { icon: UI_ICONS.paymentDetails },
      role: [1, 2, 4, 5],
    },
    {
      title: 'sms',
      to: { name: 'sms-sms' },
      icon: { icon: UI_ICONS.sms },
      role: [1, 2, 4, 5],
    },
  ]
}

export default getOperationsNavItems()
