export default [
  {
    title: 'tabs.orders_in',
    icon: { icon: 'tabler-arrow-down-left' },
    children: [
      {
        title: 'all',
        to: {
          name: 'orders-in-type',
          params: {
            type: "all",
          },
        },
        icon: { icon: 'tabler-clear-all' },
      },
      {
        title: 'active',
        to: {
          name: 'orders-in-type',
          params: {
            type: "active",
          },
        },
        icon: { icon: 'tabler-progress' },
      },
      {
        title: 'success',
        to: {
          name: 'orders-in-type',
          params: {
            type: "success",
          },
        },
        icon: { icon: 'tabler-checks' },
      },
      {
        title: 'recalculation',
        to: {
          name: 'orders-in-type',
          params: {
            type: "recalculation",
          },
        },
        icon: { icon: 'tabler-calculator' },
      },
      {
        title: 'declined',
        to: {
          name: 'orders-in-type',
          params: {
            type: "declined",
          },
        },
        icon: { icon: 'tabler-x' },
      },
      {
        title: 'arbitrage',
        to: {
          name: 'orders-in-type',
          params: {
            type: "arbitrage",
          },
        },
        icon: { icon: 'tabler-shield-lock' },
      },
    ],
    role: 1,
  },
  {
    title: 'tabs.orders_out',
    children: [
      {
        title: 'all',
        to: {
          name: 'orders-out-type',
          params: {
            type: "all",
          },
        },
        icon: { icon: 'tabler-clear-all' },
      },
      {
        title: 'active',
        to: {
          name: 'orders-out-type',
          params: {
            type: "active",
          },
        },
        icon: { icon: 'tabler-progress' },
      },
      {
        title: 'success',
        to: {
          name: 'orders-out-type',
          params: {
            type: "success",
          },
        },
        icon: { icon: 'tabler-checks' },
      },
      {
        title: 'recalculation',
        to: {
          name: 'orders-out-type',
          params: {
            type: "recalculation",
          },
        },
        icon: { icon: 'tabler-calculator' },
      },
      {
        title: 'declined',
        to: {
          name: 'orders-out-type',
          params: {
            type: "declined",
          },
        },
        icon: { icon: 'tabler-x' },
      },
      {
        title: 'manual_check',
        to: {
          name: 'orders-out-type',
          params: {
            type: "manual",
          },
        },
        icon: { icon: 'tabler-analyze' },
      },
    ],
    icon: { icon: 'tabler-arrow-up-right' },
    role: 1,
  },
  {
    title: 'payment_details',
    to: { name: 'payment-details' },
    icon: { icon: 'tabler-credit-card' },
    role: [1, 2, 4, 5],
  },
  {
    title: 'sms',
    to: { name: 'sms-sms' },
    icon: { icon: 'tabler-device-mobile-message' },
    role: [1, 2, 4, 5],
  },
]
