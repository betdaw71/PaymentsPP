import { defineStore } from 'pinia'
import instance from "@/services/api"
import { useStorage } from "@vueuse/core"

export const useSmsStore = defineStore ({
  id: 'SmsStore',
  state: () => ({
    sms_filters: useStorage ('sms_filters', {
      searchId: "",
      searchText: "",
      rowsPerPage: 20,
      searchDevice: "",
      searchDeviceOwner: "",
      searchInOrder: "",
      searchOutOrder: "",
      selectedStatus: [],
      selectedTraders: [],
      selectedTeams: [],
      dateRange: "",

      ordering: "-date",
      apply_filters: true,
    }),
  }),
  actions: {
    async getSms (params) {
      const response = await instance.get (`/sms/sms/`, { params })
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
    async getFiltersSms (params) {
      const response = await instance.get (`/sms/get-filters/`, { params })
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
