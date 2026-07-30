import { defineStore } from 'pinia'
import instance from "@/services/api"

export const useMerchantStore = defineStore ({
  id: 'MerchantStore',
  actions: {
    async getMerchant (params) {
      const response = await instance.get (`/merchant/merchant/`, { params })
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
    async getMerchantById (params, id) {
      const response = await instance.get (`/merchant/merchant/${id}`, { params })
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
    async createMerchant (params) {
      const response = await instance.post (`/merchant/merchant/`, params)
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
    async getMerchantFees (params) {
      const response = await instance.get (`/merchant/get-fees/`, { params })
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
    async deleteMerchantFee (params, id) {
      const response = await instance.delete (`/merchant/merchant-fees/${id}/`, { params })
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
    async createMerchantFee (params) {
      const response = await instance.post (`/merchant/merchant-fees/`, params)
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
    async updateMerchantById (params, id) {
      const response = await instance.patch (`/merchant/merchant/${id}/`, params)
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
    async getMerchantAgentAssignments (params) {
      const response = await instance.get (`/merchant/merchant-agent/`, { params })
      if (response.status === 200) {
        return { data: response.data, error: null }
      }
      return { data: [], error: response.data }
    },
    async createMerchantAgentAssignment (params) {
      const response = await instance.post (`/merchant/merchant-agent/`, params)
      if (response.status === 201) {
        return { data: response.data, error: null }
      }
      return { data: [], error: response.data }
    },
    async patchMerchantAgentAssignment (params, id) {
      const response = await instance.patch (`/merchant/merchant-agent/${id}/`, params)
      if (response.status === 200) {
        return { data: response.data, error: null }
      }
      return { data: [], error: response.data }
    },
    async deleteMerchantAgentAssignment (id) {
      const response = await instance.delete (`/merchant/merchant-agent/${id}/`)
      if (response.status === 204) {
        return { data: null, error: null }
      }
      return { data: null, error: response.data }
    },
  },
})
