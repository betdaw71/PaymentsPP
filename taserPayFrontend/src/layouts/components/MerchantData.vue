<script setup>
const balanceRoute = { name: 'user', query: { tab: 'balance' } }
</script>

<template>
  <ApHeaderBalance :to="balanceRoute" />
</template>
