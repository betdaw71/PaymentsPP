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


import UserBioPanel from '@/views/user/UserBioPanel.vue'
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






const tabs = computed(
  () => {

    const mainInfoTab = {
      key: 'main_info',
      icon: 'tabler-info-circle',
      title: t ('tabs.main_info'),
    }

    const teamTab = {
      key: 'team',
      icon: 'tabler-vector-triangle',
      title: t ('tabs.team'),
    }

    const balanceTab = {
      key: 'balance',
      icon: 'tabler-wallet',
      title: t ('tabs.balance'),
    }

    const transactionsTab = {
      key: 'transactions',
      icon: 'tabler-layout-list',
      title: t ('tabs.transactions'),
    }

    const withdrawalsTab = {
      key: 'withdrawals',
      icon: 'tabler-stack-pop',
      title: t ('tabs.withdrawals'),
    }

    const tradersBalanceTab = {
      key: 'traders_balance',
      icon: 'tabler-coin',
      title: t ('tabs.traders_balance'),
    }

    const merchantsBalanceTab = {
      key: 'merchants_balance',
      icon: 'tabler-coin',
      title: t ('tabs.merchants_balance'),
    }

    const merchantsApiTab = {
      key: 'merchants_api',
      icon: 'tabler-api',
      title: t ('tabs.merchants_api'),
    }

    const dashboardTab = {
      key: 'dashboard',
      icon: 'tabler-chart-histogram',
      title: t ('tabs.dashboard'),
    }

    if (authStore.is_senior_trader ())
      return [
        mainInfoTab,
        teamTab,
        balanceTab,
        transactionsTab,
        withdrawalsTab,
      ]
    if (authStore.is_trader ())
      return [
        mainInfoTab,
        teamTab,
        balanceTab,
        transactionsTab,
      ]
    if (authStore.is_merchant_assist ()) {
      return [
        mainInfoTab,
        balanceTab,
        transactionsTab,
      ]
    }
    if (authStore.is_team_lead ()) {
      return [
        mainInfoTab,
        balanceTab,
        transactionsTab,
        withdrawalsTab,
      ]
    }
    if (authStore.is_merchant ()) {
      return [
        mainInfoTab,
        balanceTab,
        transactionsTab,
        withdrawalsTab,
        merchantsApiTab,
      ]
    }
    if (authStore.is_head_of_support ()) {
      return [
        dashboardTab,
        mainInfoTab,
        teamTab,
        transactionsTab,
        tradersBalanceTab,
        merchantsBalanceTab,
        withdrawalsTab,
      ]
    }
    if (authStore.is_support ()) {
      return [
        mainInfoTab,
        teamTab,
        transactionsTab,
        tradersBalanceTab,
        withdrawalsTab,
      ]
    }

    return [
      mainInfoTab,
      teamTab,
      balanceTab,
      transactionsTab,
    ]
  },
)

const resolveTabIndex = tabKey => {
  if (!tabKey) {
    return -1
  }

  return tabs.value.findIndex (tab => tab.key === tabKey)
}

const activeTabIndex = computed (() => {
  const index = resolveTabIndex (String (route.query.tab || ''))

  return index >= 0 ? index : 0
})

const activeSection = computed (() => tabs.value[activeTabIndex.value])

watch (
  () => route.query.tab,
  tabKey => {
    const index = resolveTabIndex (String (tabKey || ''))
    if (index >= 0) {
      profileSettings.value.user_info_tab = index
    }
  },
  { immediate: true },
)

watch (
  () => [userData.value, tabs.value.length, route.query.tab],
  () => {
    if (!userData.value || !tabs.value.length) {
      return
    }
    if (!route.query.tab && tabs.value[0]?.key) {
      router.replace ({ name: 'user', query: { tab: tabs.value[0].key } })
    }
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
  <ApWorkspace v-if="userData">
      <template #header>
        <ApPageHeader
          v-if="activeSection"
          :title="activeSection.title"
          :subtitle="activeSection.key === 'dashboard' ? $t('nav.analytics') : $t('nav.finance')"
        />
      </template>

      <VAlert
        v-if="!authStore.userData.deposit"
        variant="tonal"
        color="error"
        class="mb-4"
      >
        <VAlertTitle class="mb-1">
          {{ $t('alerts.balance_low.requirements_description') }}
        </VAlertTitle>
        <span>
          {{ $t('alerts.balance_low.requirements') }}</span>
      </VAlert>

      <VWindow
        :model-value="activeTabIndex"
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
  </ApWorkspace>
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
          icon="tabler-tick"
        />
        <VIcon
          v-else
          color="error"
          icon="tabler-x"
        />
      </div>
    </VCardItem>
  </template>
</template>
