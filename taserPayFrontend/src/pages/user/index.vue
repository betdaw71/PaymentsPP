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


import { tabQueryKeys } from '@/design/tokens'


const { t } = useI18n ()
const pollingThreshold = ref (120)
const route = useRoute ()
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
      icon: 'tabler-info-circle',
      title: t ('tabs.main_info'),
    }

    const teamTab = {
      icon: 'tabler-vector-triangle',
      title: t ('tabs.team'),
    }

    const balanceTab = {
      icon: 'tabler-wallet',
      title: t ('tabs.balance'),
    }

    const transactionsTab = {
      icon: 'tabler-layout-list',
      title: t ('tabs.transactions'),
    }

    const withdrawalsTab = {
      icon: 'tabler-stack-pop',
      title: t ('tabs.withdrawals'),
    }

    const tradersBalanceTab = {
      icon: 'tabler-coin',
      title: t ('tabs.traders_balance'),
    }

    const merchantsBalanceTab = {
      icon: 'tabler-coin',
      title: t ('tabs.merchants_balance'),
    }

    const merchantsApiTab = {
      icon: 'tabler-api',
      title: t ('tabs.merchants_api'),
    }

    const dashboardTab = {
      icon: 'tabler-chart-dots-3',
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

  const i18nKey = tabQueryKeys[tabKey]
  if (!i18nKey) {
    return -1
  }

  const label = t (i18nKey)

  return tabs.value.findIndex (tab => tab.title === label)
}

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
  <VRow v-if="userData">
    <!--    <VCol -->
    <!--      cols="12" -->
    <!--      md="3" -->
    <!--      lg="3" -->
    <!--    > -->
    <!--      <UserBioPanel -->
    <!--        v-model:user-data="userData" -->
    <!--        @update:userData="userData = $event" -->
    <!--      /> -->
    <!--    </VCol> -->

    <VCol
      cols="12"
    >
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
      <VTabs
        v-model="profileSettings.user_info_tab"
        class="v-tabs-pill"
        show-arrows
      >
        <VTab
          v-for="tab in tabs"
          :key="tab.icon"
          class="me-1"
        >
          <VIcon
            :size="18"
            :icon="tab.icon"
            class="me-1"
          />
          <span>{{ tab.title }}</span>
        </VTab>
      </VTabs>

      <VWindow
        v-model="profileSettings.user_info_tab"
        class="mt-6 disable-tab-transition"
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
    </VCol>
  </VRow>
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
