import { defineStore } from 'pinia'
import instance from "@/services/api"

export const useTradeStore = defineStore ({
  id: 'TradeStore',
  actions: {
    async getTradeOrderIn (params) {
      const response = await instance.get (`/trade/order/in/`, { params })
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
    async exportTradeOrderIn (params) {
      const response = await instance.get (`/trade/order/in/export/`, { params })
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
    async createTradeOrderIn (params) {
      const response = await instance.post (`/trade/order/in/`, params)
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
    async getTradeOrderInById (params, id) {
      const response = await instance.get (`/trade/order/in/${id}/`, { params })
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
    async changeTradeOrderInArbitrageById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/arbitrage/`, params)
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
    async changeTradeOrderInCancelById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/cancel/`, params)
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
    async changeTradeOrderInCompleteById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/complete/`, params)
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
    async changeTradeOrderInCompleteSupportById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/complete-support/`, params)
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
    async changeTradeOrderInArbitrageSupportById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/arbitrage-support/`, params, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

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
    async changeTradeOrderInCallbackById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/callback/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        error: response.data,
      }
    },
    async changeTradeOrderOutCallbackById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/callback/`, params)
      if (response.status === 200) {
        return {
          data: response.data,
          error: null,
        }
      }

      return {
        error: response.data,
      }
    },
    async changeTradeOrderInExpiredById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/expired/`, params)
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
    async changeTradeOrderInMoneySentById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/money-sent/`, params)
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
    async getTradeTransaction (params) {
      const response = await instance.get (`/trade/transaction/`, { params })
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
    async getTradeTransactionById (params, id) {
      const response = await instance.get (`/trade/transaction/${id}/`, { params })
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
    async getTradeWithdrawalRequest (params) {
      const response = await instance.get (`/trade/withdrawal-request/`, { params })
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
    async createTradeWithdrawalRequest (params) {
      const response = await instance.post (`/trade/withdrawal-request/`, params)
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
    async getTradeWithdrawalRequestById (params, id) {
      const response = await instance.get (`/trade/withdrawal-request/${id}`, { params })
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
    async approveTradeWithdrawalRequestById (params, id) {
      const response = await instance.post (`/trade/withdrawal-request/${id}/approve/`, params)
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
    async rejectTradeWithdrawalRequestById (params, id) {
      const response = await instance.post (`/trade/withdrawal-request/${id}/reject/`, params)
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
    async getTradeOrderOut (params) {
      const response = await instance.get (`/trade/order/out/`, { params })
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
    async exportTradeOrderOut (params) {
      const response = await instance.get (`/trade/order/out/export/`, { params })
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
    async createTradeOrderOut (params) {
      const response = await instance.post (`/trade/order/out/`, params)
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
    async getTradeOrderOutById (params, id) {
      const response = await instance.get (`/trade/order/out/${id}/`, { params })
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
    async changeTradeOrderOutArbitrageSupportById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/arbitrage/`, params)
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
    async changeTradeOrderOutCancelSupportById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/cancel/`, params)
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
    async changeTradeOrderOutCompleteSupportById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/complete-support/`, params)
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
    async changeTradeOrderOutCompleteTraderById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/complete-trader/`, params, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

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
    async changeTradeOrderOutResetById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/reset/`, params)
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
    async changeTradeOrderOutCannotProcessById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/cannot-process/`, params)
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
    async changeTradeOrderOutMoneySentById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/money-sent/`, params)
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
    async getFiltersOrderIn (params) {
      try {
        const response = await instance.get (`/trade/get-filters-order/in/`, { params })
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
      } catch (e) {
        console.log ({ e })

        return {
          data: [],
          error: response.data,
        }
      }
    },
    async getFiltersOrderOut (params) {
      const response = await instance.get (`/trade/get-filters-order/out/`, { params })
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
    async getReasonsOrderOut (params) {
      const response = await instance.get (`/trade/order/out/reasons/`, { params })
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
    async getReasonsOrderIn (params) {
      const response = await instance.get (`/trade/order/in/reasons/`, { params })
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
    async recalculateTradeOrderOutById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/recalculate/`, params, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      })

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
    async recalculateTradeOrderInById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/recalculate/`, params)
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
    async moveTradeOrderInById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/move/`, params)
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
    async callbackTradeOrderInById (params, id) {
      const response = await instance.post (`/trade/order/in/${id}/callback/`, params)
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
    async callbackTradeOrderOutById (params, id) {
      const response = await instance.post (`/trade/order/out/${id}/callback/`, params)
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
    async deleteRate (params, id) {
      const response = await instance.delete (`/trade/rates/${id}/`, { params })
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
    async createRate (params) {
      const response = await instance.post (`/trade/rates/`, params)
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
  },
})
