<script setup>
import { useAuthStore } from '@/stores/useAuthStore'

const props = defineProps({
  showIncome: {
    type: Boolean,
    default: false,
  },
  to: {
    type: Object,
    default: null,
  },
})

const authStore = useAuthStore()
const router = useRouter()

const fmt = value => {
  const num = Number(value ?? 0)

  return num.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

const available = computed(() => authStore.userData.current_balance ?? 0)
const income = computed(() => authStore.userData.income ?? 0)
const frozen = computed(() => authStore.userData.hold ?? 0)

const navigate = () => {
  if (props.to) {
    router.push(props.to)
  }
}
</script>

<template>
  <div
    class="ap-header-balance d-none d-md-flex"
    :class="{ 'ap-header-balance--clickable': !!to }"
    @click="to ? navigate() : undefined"
  >
    <div class="ap-surface-chip ap-surface-chip--primary">
      <span class="ap-surface-chip__label">{{ $t('balance') }}</span>
      <span class="ap-surface-chip__value">${{ fmt(available) }}</span>
    </div>
    <div
      v-if="showIncome"
      class="ap-surface-chip ap-surface-chip--income"
    >
      <span class="ap-surface-chip__label">{{ $t('income') }}</span>
      <span class="ap-surface-chip__value">${{ fmt(income) }}</span>
    </div>
    <div class="ap-surface-chip ap-surface-chip--frozen">
      <span class="ap-surface-chip__label">{{ $t('hold') }}</span>
      <span class="ap-surface-chip__value">${{ fmt(frozen) }}</span>
    </div>
  </div>
</template>
