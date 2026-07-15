import { defineStore } from 'pinia'
import instance from "@/services/api"
import { useStorage } from "@vueuse/core"

export const useBaseStore = defineStore ({
  id: 'BaseStore',
  state: () => ({
    transactions_filters: useStorage ('transactions_filters', {
      searchQueryId: "",
      rowsPerPage: 20,
      selectedType: [],
      minAmount: 0,
      maxAmount: 0,
      searchQueryIn: "",
      searchQueryOut: "",
      dateRange: "",
      from: {
        balance__available__user__username__in: [],
        balance__available_merchant__user__username__in: [],
        balance__available__team__name__in: [],
        balance__type__in: [],
      },
      to: {
        balance__available__user__username__in: [],
        balance__available_merchant__user__username__in: [],
        balance__available__team__name__in: [],
        balance__type__in: [],
      },
      ordering: "-creation_date",
      direction: "all",
    }),
    withdrawals_filters: useStorage ('withdrawals_filters', {
      searchQueryId: "",
      rowsPerPage: 20,
      selectedType: [],
      minAmount: 0,
      maxAmount: 0,
      searchQueryComment: "",
      searchQueryAddress: "",
      dateRange: "",
      selectedTarget: [],
      ordering: "-date",
    }),
    orders_in_filters: useStorage ('orders_in_filters', {
      searchQueryId: "",
      rowsPerPage: 20,
      searchPaymentDetailsGroupId: "",
      searchPaymentDetailsGroupOwner: "",
      searchCustomerId: "",
      selectedStatus: [],
      selectedPaymentSystems: [],
      selectedMerchants: [],
      selectedCurrencies: [],
      selectedTrafficTypes: [],
      selectedTraders: [],
      selectedTeams: [],
      searchMerchantOrderId: "",
      searchPaymentDetailsId: "",
      searchTransactionId: "",
      minAmount: 0,
      maxAmount: 0,
      minUSDAmount: 0,
      maxUSDAmount: 0,
      dateRange: "",
      ordering: "-creation_date",
      autoUpdateMode: 30,
      apply_filters: true,
    }),
    orders_out_filters: useStorage ('orders_out_filters', {
      searchQueryId: "",
      rowsPerPage: 20,
      searchPaymentDetailsGroupId: "",
      searchPaymentDetailsGroupOwner: "",
      searchCustomerId: "",
      selectedStatus: [],
      selectedPaymentSystems: [],
      selectedMerchants: [],
      selectedCurrencies: [],
      selectedTrafficTypes: [],
      selectedTraders: [],
      selectedTeams: [],
      searchMerchantOrderId: "",
      searchPaymentDetailsId: "",
      searchTransactionId: "",
      minAmount: 0,
      maxAmount: 0,
      minUSDAmount: 0,
      maxUSDAmount: 0,
      dateRange: "",
      ordering: "-creation_date",
      autoUpdateMode: 30,
      apply_filters: true,
    }),
    payment_details_filters: useStorage ('payment_details_filters', {
      searchOwner: "",
      rowsPerPage: 20,
      selectedStatus: [],
      selectedPaymentSystems: [],
      selectedCurrencies: [],
      selectedTrafficTypes: [],
      selectedTraders: [],
      selectedTeams: [],

      ordering: "-total_volume",
      apply_filters: true,
    }),
    payment_details_statistics: useStorage ('payment_details_statistics', {
      currency: "",
    }),
    profile_settings: useStorage ('profile_settings', {
      user_info_tab: null,
    }),
    balance_settings: useStorage ('balance_settings', {
      currency_tab: null,
      team_tab: null,
    }),
    team_settings: useStorage ('team_settings', {
      tab: null,
    }),
    add_settings: useStorage ('add_settings', {
      tab: null,
    }),
  }),
  actions: {
    async getAddress (params) {
      const response = await instance.get (`/base/address/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getAddressById (params, id) {
      const response = await instance.get (`/base/address/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getBalance (params) {
      const response = await instance.get (`/base/balance/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getBalances (params) {
      const response = await instance.get (`/base/get-balances/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getBalanceById (params, id) {
      const response = await instance.get (`/base/balance/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async createBalance (params) {
      const response = await instance.post (`/base/balance/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getBalanceMerchant (params) {
      const response = await instance.get (`/base/balance/merchant/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getBalanceTeamLead (params) {
      const response = await instance.get (`/base/balance/teamlead/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getBalanceSupport (params) {
      const response = await instance.get (`/base/balance/support/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getBalanceSupportMerchant (params) {
      const response = await instance.get (`/base/balance/support-merchant/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getBalanceTrader (params) {
      const response = await instance.get (`/base/balance/trader/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async transferBalance (params) {
      const response = await instance.post (`/base/balance/transfer/`, params)
      if (response.status === 201) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getCurrency (params) {
      const response = await instance.get (`/base/currency/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getCurrencyById (params, id) {
      const response = await instance.get (`/base/currency/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getLanguage (params) {
      const response = await instance.get (`/base/language/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getLanguageById (params, id) {
      const response = await instance.get (`/base/language/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getPaymentDetails (params) {
      const response = await instance.get (`/base/details/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getPaymentDetailsById (params, id) {
      const response = await instance.get (`/base/details/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async createPaymentDetails (params) {
      const response = await instance.post (`/base/details/`, params)
      if (response.status === 201) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async updatePaymentDetailsById (params, id) {
      const response = await instance.put (`/base/details/${id}/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async changePaymentDetailsDirectionStatusById (params, id) {
      const response = await instance.post (`/base/details/${id}/in-out/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async updatePaymentDetailLimitsById (params, id) {
      const response = await instance.post (`/base/details/${id}/set-limits/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async changePaymentDetailsArbitrageUnblockStatusById (params, id) {
      const response = await instance.post (`/base/details/${id}/arb-unblock/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async changePaymentDetailsWorkStatusById (params, id) {
      const response = await instance.post (`/base/details/${id}/change-status/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async changePaymentDetailsDepositModeById (params, id) {
      const response = await instance.post (`/base/details/${id}/dep-mode/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async addPaymentDetailToDetailsById (params, id) {
      const response = await instance.post (`/base/details/${id}/add-details/`, params)
      if (response.status === 201) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async changePaymentDetailToDetailsById (params, id) {
      const response = await instance.post (`/base/details/${id}/change-details-status/`, params)
      if (response.status === 201) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getPaymentDetailsStatsById (params, id) {
      const response = await instance.get (`/base/details/${id}/stats/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getPaymentSystem (params) {
      const response = await instance.get (`/base/payment-system/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async createPaymentSystem (params) {
      const response = await instance.post (`/base/payment-system-create/`, params)
      if (response.status === 201) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getPaymentSystemById (params, id) {
      const response = await instance.get (`/base/payment-system/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getSupportMember (params) {
      const response = await instance.get (`/base/support-member/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getTeamLead (params) {
      const response = await instance.get (`/base/teamlead/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getSupportMemberById (params, id) {
      const response = await instance.get (`/base/support-member/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async createSupportMember (params) {
      const response = await instance.post (`/base/support-member/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async updateSupportMemberById (params, id) {
      const response = await instance.patch (`/base/support-member/${id}/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getTraderTeam (params) {
      const response = await instance.get (`/base/trader-team/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getTraderTeamById (params, id) {
      const response = await instance.get (`/base/trader-team/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async setTraderTeamRatesById (params, id) {
      const response = await instance.post (`/base/trader-team/${id}/set_rates/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async createTraderTeam (params) {
      const response = await instance.post (`/base/trader-team/`, params)
      if (response.status === 201) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getTradingTeamSupport (params) {
      const response = await instance.get (`/base/trading-team/support/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getExchangeRates (params) {
      const response = await instance.get (`/base/exchange-rates/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getDashboard (params) {
      const response = await instance.get (`/base/dashboard/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: null,
        error: response.data,
      }
    },
    async getTradingTeamTrader (params) {
      const response = await instance.get (`/base/trading-team/trader/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getTrader (params) {
      const response = await instance.get (`/base/trader/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getTraderById (params, id) {
      const response = await instance.get (`/base/trader/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async createTrader (params) {
      const response = await instance.post (`/base/trader/`, params)
      if (response.status === 201) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async updateTraderById (params, id) {
      const response = await instance.patch (`/base/trader/${id}/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async deleteTraderById (params, id) {
      const response = await instance.delete (`/base/trader/${id}/`, params)
      if (response.status === 204) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async blockTraderPaymentDetailsCreationById (params, id) {
      const response = await instance.post (`/base/trader/${id}/block/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async unblockTraderPaymentDetailsCreationById (params, id) {
      const response = await instance.post (`/base/trader/${id}/unblock/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getTransferTargets (params) {
      const response = await instance.get (`/base/transfer-targets/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },

    async getTrafficType (params) {
      const response = await instance.get (`/base/traffic-type/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getTrafficTypeById (params, id) {
      const response = await instance.get (`/base/traffic-type/${id}/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getSupportBalanceTargets (params) {
      const response = await instance.get (`/base/balance-targets/support/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getWithdrawalTargets (params) {
      const response = await instance.get (`/base/withdrawal-targets/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getTraderBalanceTargets (params) {
      const response = await instance.get (`/base/balance-targets/trader/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getFiltersPaymentDetails (params) {
      const response = await instance.get (`/base/get-filters-pd/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getPaymentDetailsCreationData (params) {
      const response = await instance.get (`/base/pd-creation-data/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getPaymentDetailsGroupCreationData (params) {
      const response = await instance.get (`/base/pdgroup-creation-data/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
    async getPaymentDetailsStatistics (params) {
      const response = await instance.get (`/base/get-stats-pd/`, { params })
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        data: [],
        error: response.data,
      }
    },
  },
})
