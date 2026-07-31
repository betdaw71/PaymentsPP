import { defineStore } from 'pinia'
import instance from "@/services/api"

function downloadExcelBlob (response, defaultName) {
  let filename = defaultName
  const disposition = response.headers['content-disposition']
  if (disposition) {
    const match = /filename="?([^";\n]+)"?/.exec(disposition)
    if (match)
      filename = match[1]
  }
  const url = window.URL.createObjectURL(new Blob([response.data]))
  const link = document.createElement('a')

  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

async function exportOrdersExcel (path, params, defaultName) {
  try {
    const response = await instance.get(path, { params, responseType: 'blob' })
    if (response.status !== 200) {
      return {
        data: [],
        error: response.data,
      }
    }

    const contentType = response.headers['content-type'] || ''
    if (contentType.includes('spreadsheetml') || contentType.includes('octet-stream')) {
      downloadExcelBlob(response, defaultName)

      return {
        data: { downloaded: true },
        error: null,
      }
    }

    try {
      const text = await response.data.text()
      const json = JSON.parse(text)
      if (json.url) {
        window.open(json.url, '_blank')

        return {
          data: json,
          error: null,
        }
      }

      return {
        data: [],
        error: json,
      }
    } catch {
      return {
        data: [],
        error: 'Export failed',
      }
    }
  } catch (error) {
    const res = error.response
    if (res?.data instanceof Blob) {
      try {
        const text = await res.data.text()
        const json = JSON.parse(text)
        const message = json.detail || json.error || json.message || text

        return {
          data: [],
          error: typeof message === 'string' ? message : JSON.stringify(message),
        }
      } catch {
        return {
          data: [],
          error: `Export failed (${res.status || 'network'})`,
        }
      }
    }

    return {
      data: [],
      error: error.message || 'Export failed',
    }
  }
}

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
      return exportOrdersExcel('/trade/order/in/export/', params, 'orders_in.xlsx')
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
      return exportOrdersExcel('/trade/order/out/export/', params, 'orders_out.xlsx')
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
