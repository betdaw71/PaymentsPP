<script setup>
import MainTraderInfo from '@/views/user/trader/MainTraderInfo.vue'
import TraderTeam from "@/views/user/trader/TraderTeam.vue"
import TraderBalance from "@/views/user/trader/TraderBalance.vue"
import TraderTransactions from "@/views/user/trader/TraderTransactions.vue"


import MainSeniorTraderInfo from '@/views/user/seniortrader/MainSeniorTraderInfo.vue'
import SeniorTraderTeam from "@/views/user/seniortrader/SeniorTraderTeam.vue"
import SeniorTraderBalance from "@/views/user/seniortrader/SeniorTraderBalance.vue"
import SeniorTraderTransactions from "@/views/user/seniortrader/SeniorTraderTransactions.vue"
import SeniorTraderWithdrawals from "@/views/user/seniortrader/SeniorTraderWithdrawals.vue"

import MainMerchantInfo from '@/views/user/merchant/MainMerchantInfo.vue'
import MerchantBalance from "@/views/user/merchant/MerchantBalance.vue"
import MerchantTransactions from "@/views/user/merchant/MerchantTransactions.vue"
import MerchantWithdrawals from "@/views/user/merchant/MerchantWithdrawals.vue"

import MainMerchantAssistInfo from '@/views/user/merchantassist/MainMerchantAssistInfo.vue'
import MerchantAssistBalance from "@/views/user/merchantassist/MerchantAssistBalance.vue"
import MerchantAssistTransactions from "@/views/user/merchantassist/MerchantAssistTransactions.vue"
import MerchantAssistWithdrawals from "@/views/user/merchantassist/MerchantAssistWithdrawals.vue"

import MainTeamLeadInfo from '@/views/user/teamlead/MainTeamLeadInfo.vue'
import TeamLeadBalance from "@/views/user/teamlead/TeamLeadBalance.vue"
import TeamLeadTransactions from "@/views/user/teamlead/TeamLeadTransactions.vue"
import TeamLeadWithdrawals from "@/views/user/teamlead/TeamLeadWithdrawals.vue"

import MainSupportInfo from "@/views/user/support/MainSupportInfo.vue"
import SupportTeam from "@/views/user/support/SupportTeam.vue"
import SupportTransactions from "@/views/user/support/SupportTransactions.vue"
import SupportTradersBalance from "@/views/user/support/SupportTradersBalance.vue"
import SupportWithdrawals from "@/views/user/support/SupportWithdrawals.vue"

import MainHeadSupportInfo from '@/views/user/headsupport/MainHeadSupportInfo.vue'
import HeadSupportTeam from "@/views/user/headsupport/HeadSupportTeam.vue"
import HeadSupportTransactions from "@/views/user/headsupport/HeadSupportTransactions.vue"
import HeadSupportTradersBalance from "@/views/user/headsupport/HeadSupportTradersBalance.vue"
import HeadSupportMerchantsBalance from "@/views/user/headsupport/HeadSupportMerchantsBalance.vue"
import HeadSupportWithdrawals from "@/views/user/headsupport/HeadSupportWithdrawals.vue"
import HeadSupportDashboard from "@/views/user/headsupport/HeadSupportDashboard.vue"


import { getProfileTabs } from '@/navigation/profile-tabs'
import { UI_ICONS } from '@/constants/ui-icons'
import { useAuthStore } from "@/stores/useAuthStore"
import MerchantApiKeys from "@/views/user/merchant/MerchantApiKeys.vue"
import { useBaseStore } from "@/stores/useBaseStore"

const { t } = useI18n ()
const pollingThreshold = ref (120)
const route = useRoute ()
const router = useRouter ()
const authStore = useAuthStore ()
const baseStore = useBaseStore ()
const userData = ref (null)

const profileSettings = ref(
  structuredClone (toRaw (baseStore.profile_settings)),
)

watch (
  () => profileSettings.value,
  () => {
    baseStore.profile_settings = structuredClone (toRaw (profileSettings.value))
  },
  { deep: true },
)

const userPolling = ref (null)

const loadMessage = ref ({
  message: t ('data.loading'),
  status: 0,
})

onBeforeMount (
  () => {
    getUser ()
    userPolling.value = setInterval (
      getUser,
      5000,
    )
  },
)
onUnmounted (
  () => {
    clearInterval (userPolling.value)
  },
)






const profileTabs = computed(() => getProfileTabs(authStore))

const activeTabIndex = computed({
  get () {
    const tabKey = route.query.tab
    if (tabKey) {
      const idx = profileTabs.value.findIndex(tab => tab.key === tabKey)
      if (idx >= 0)
        return idx
    }

    return profileSettings.value.user_info_tab ?? 0
  },
  set (idx) {
    profileSettings.value.user_info_tab = idx
    const tab = profileTabs.value[idx]
    if (tab && route.query.tab !== tab.key)
      router.replace({ name: 'user', query: { tab: tab.key } })
  },
})

const currentTab = computed(() => profileTabs.value[activeTabIndex.value])

watch(
  () => route.query.tab,
  tabKey => {
    if (!profileTabs.value.length)
      return

    if (!tabKey) {
      const preferred = profileTabs.value.find(tab => tab.key === 'balance') || profileTabs.value[0]
      router.replace({ name: 'user', query: { tab: preferred.key } })

      return
    }

    const idx = profileTabs.value.findIndex(tab => tab.key === tabKey)
    if (idx >= 0)
      profileSettings.value.user_info_tab = idx
  },
  { immediate: true },
)

const getUser = (polling = true) => {
  if (polling && pollingThreshold.value <= 0) {
    return
  } else if (!polling) {
    loadMessage.value = {
      message: t ('data.loading'),
      status: 0,
    }
  }
  pollingThreshold.value -= 1
  authStore.me ().then (
    () => {
      userData.value = authStore.userData
    },
  ).catch (
    err => {
      loadMessage.value = {
        message: t ('data.user.loading_error'),
        status: 2,
      }
    },
  )
}
</script>

<template>
  <UiWorkspace
    v-if="userData"
    :no-padding="false"
  >
    <template #header>
      <div class="ui-workspace__title-row">
        <VAvatar
          size="40"
          variant="text"
          color="primary"
          :icon="currentTab?.icon || UI_ICONS.profile"
        />
        <div>
          <h1 class="ui-workspace__title">
            {{ currentTab ? $t(currentTab.title) : $t('user.profile.title') }}
          </h1>
          <p class="ui-workspace__subtitle">
            {{ $t('user.profile.title') }}
          </p>
        </div>
      </div>
    </template>

    <VAlert
      v-if="!authStore.userData.deposit"
      variant="tonal"
      color="error"
      class="mb-4 mx-4 mt-3"
    >
      <VAlertTitle class="mb-1">
        {{ $t('alerts.balance_low.requirements_description') }}
      </VAlertTitle>
      <span>{{ $t('alerts.balance_low.requirements') }}</span>
    </VAlert>

    <nav
      v-if="profileTabs.length > 1"
      class="ui-profile-tabs"
      :aria-label="$t('user.profile.title')"
    >
      <button
        v-for="(tab, idx) in profileTabs"
        :key="tab.key"
        type="button"
        class="ui-profile-tabs__item"
        :class="{ 'ui-profile-tabs__item--active': activeTabIndex === idx }"
        @click="activeTabIndex = idx"
      >
        {{ $t(tab.title) }}
      </button>
    </nav>

    <div>
      <VWindow
        v-model="activeTabIndex"
        class="disable-tab-transition"
        :touch="false"
      >
        <template
          v-if="authStore.is_senior_trader()"
        >
          <VWindowItem>
            <MainSeniorTraderInfo />
          </VWindowItem>
          <VWindowItem>
            <SeniorTraderTeam />
          </VWindowItem>
          <VWindowItem>
            <SeniorTraderBalance />
          </VWindowItem>
          <VWindowItem>
            <SeniorTraderTransactions />
          </VWindowItem>
          <VWindowItem>
            <SeniorTraderWithdrawals />
          </VWindowItem>
        </template>
        <template
          v-else-if="authStore.is_trader()"
        >
          <VWindowItem>
            <MainTraderInfo />
          </VWindowItem>
          <VWindowItem>
            <TraderTeam />
          </VWindowItem>
          <VWindowItem>
            <TraderBalance />
          </VWindowItem>
          <VWindowItem>
            <TraderTransactions />
          </VWindowItem>
        </template>
        <template
          v-else-if="authStore.is_merchant_assist()"
        >
          <VWindowItem>
            <MainMerchantAssistInfo />
          </VWindowItem>
          <VWindowItem>
            <MerchantAssistBalance />
          </VWindowItem>
          <VWindowItem>
            <MerchantAssistTransactions />
          </VWindowItem>
        </template>
        <template
          v-else-if="authStore.is_team_lead()"
        >
          <VWindowItem>
            <MainTeamLeadInfo />
          </VWindowItem>
          <VWindowItem>
            <TeamLeadBalance />
          </VWindowItem>
          <VWindowItem>
            <TeamLeadTransactions />
          </VWindowItem>
          <VWindowItem>
            <TeamLeadWithdrawals />
          </VWindowItem>
        </template>
        <template
          v-else-if="authStore.is_merchant()"
        >
          <VWindowItem>
            <MainMerchantInfo />
          </VWindowItem>
          <VWindowItem>
            <MerchantBalance />
          </VWindowItem>
          <VWindowItem>
            <MerchantTransactions />
          </VWindowItem>
          <VWindowItem>
            <MerchantWithdrawals />
          </VWindowItem>
          <VWindowItem>
            <MerchantApiKeys />
          </VWindowItem>
        </template>
        <template
          v-else-if="authStore.is_head_of_support()"
        >
          <VWindowItem>
            <HeadSupportDashboard />
          </VWindowItem>
          <VWindowItem>
            <MainHeadSupportInfo />
          </VWindowItem>
          <VWindowItem>
            <HeadSupportTeam />
          </VWindowItem>
          <VWindowItem>
            <HeadSupportTransactions />
          </VWindowItem>
          <VWindowItem>
            <HeadSupportTradersBalance />
          </VWindowItem>
          <VWindowItem>
            <HeadSupportMerchantsBalance />
          </VWindowItem>
          <VWindowItem>
            <HeadSupportWithdrawals />
          </VWindowItem>
        </template>
        <template
          v-else-if="authStore.is_support()"
        >
          <VWindowItem>
            <MainSupportInfo />
          </VWindowItem>
          <VWindowItem>
            <SupportTeam />
          </VWindowItem>
          <VWindowItem>
            <SupportTransactions />
          </VWindowItem>
          <VWindowItem>
            <SupportTradersBalance />
          </VWindowItem>
          <VWindowItem>
            <SupportWithdrawals />
          </VWindowItem>
        </template>
      </VWindow>
    </div>
  </UiWorkspace>
  <template v-else>
    <VCardItem>
      <div
        colspan="12"
        class="text-center text-body-1 justify-center align-center"
      >
        {{ loadMessage.message }}
        <VProgressCircular
          v-if="loadMessage.status === 0"
          :width="3"
          color="primary"
          indeterminate
        />
        <VIcon
          v-else-if="loadMessage.status === 1"
          color="success"
          icon="lucide-check"
        />
        <VIcon
          v-else
          color="error"
          icon="lucide-x"
        />
      </div>
    </VCardItem>
  </template>
</template>
