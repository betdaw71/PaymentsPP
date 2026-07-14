<script setup>
import Notifications from '@core/components/Notifications.vue'
import { useAuthStore } from "@/stores/useAuthStore"

const authStore = useAuthStore ()

// Images
// import avatar3 from '@images/avatars/avatar-3.png'
// import avatar4 from '@images/avatars/avatar-4.png'
// import avatar5 from '@images/avatars/avatar-5.png'
// import paypal from '@images/svg/paypal.svg'

// const notifications = [
//   {
//     title: 'Congratulation Flora! 🎉',
//     subtitle: 'Won the monthly best seller badge',
//     time: 'Today',
//   },
//   {
//     text: 'Tom Holland',
//     title: 'New user registered.',
//     subtitle: '5 hours ago',
//     time: 'Yesterday',
//   },
//   {
//     title: 'New message received 👋🏻',
//     subtitle: 'You have 10 unread messages',
//     time: '11 Aug',
//   },
//   {
//     title: 'Paypal',
//     subtitle: 'Received Payment',
//     time: '25 May',
//     color: 'error',
//   },
//   {
//     title: 'Received Order 📦',
//     subtitle: 'New order received from john',
//     time: '19 Mar',
//   },
// ]

const notificationsInterval = ref(null)

const notifications = ref({
  active: false,
  content: [],
})

const loadNotifications = () => {
  if (authStore.is_authenticated ()) {
    authStore.getNotifications ({}).then(
      response => {
        notifications.value = response.data
      },
    )
  }
}

onMounted (
  () => {
    loadNotifications ()
    notificationsInterval.value = setInterval (
      () => {
        loadNotifications ()
      },
      1000 * 30, // 30 seconds
    )
  },
)
</script>

<template>
  <Notifications :notifications="notifications" />
</template>
