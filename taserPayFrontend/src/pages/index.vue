<script setup>
const router = useRouter ()

onMounted (
  () => {
    router.push ({ name: 'orders-in-type', params: { type: "all" } })
  },
)
</script>

<template>
  <span />
</template>
