import { UI_ICONS } from '@/constants/ui-icons'

export function getOperationsNavItems () {
  return [
    {
      title: 'tabs.orders_in',
      to: { name: 'orders-in-type', params: { type: 'all' } },
      activeMatch: { name: 'orders-in-type' },
      icon: { icon: UI_ICONS.ordersIn },
      role: 1,
    },
    {
      title: 'tabs.orders_out',
      to: { name: 'orders-out-type', params: { type: 'all' } },
      activeMatch: { name: 'orders-out-type' },
      icon: { icon: UI_ICONS.ordersOut },
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
