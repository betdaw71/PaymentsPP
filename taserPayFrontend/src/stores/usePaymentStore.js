import { defineStore } from 'pinia'
import instance from "@/services/api"

export const usePaymentStore = defineStore ({
  id: 'PaymentStore',
  actions: {
    async getKey (params) {
      const response = await instance.get (`/payments/keys/`, { params })
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
    async generateKey (params) {
      const response = await instance.post (`/payments/keys/`, params)
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
    async getKeyById (params, id) {
      const response = await instance.get (`/payments/keys/${id}/`, { params })
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
    async updateKeyWhitelistById (params, id) {
      const response = await instance.post (`/payments/keys/${id}/whitelist/`, params)
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
