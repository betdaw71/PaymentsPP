import { defineStore } from 'pinia'
import { useStorage } from '@vueuse/core'
import instance from "@/services/api"
import EventBus from "@/services/EventBus"

export const useAuthStore = defineStore ({
  id: 'AuthStore',
  state: () => ({
    userData: useStorage ('userData', {
      object_id: "",
      username: "",
      first_name: "",
      email: "",
      language: "English",
      telegram: "",
      phone: "",
      currency: "INR",
      position: "",
      role: 0,
      payment_systems: [],
      deposit: true,
      has_merchant_agent: false,
    }),
    authData: useStorage ('authData', {
      'maintenance': false,
      'access': '',
      'refresh': '',
      'nextUrl': 'index',
    }),
  }),
  actions: {
    is_authenticated () {
      return !!this.authData.access
    },
    is_merchant () {
      return this.userData.role === 3 || this.userData.role === 6 || this.userData.role === 7
    },
    is_merchant_admin () {
      return this.userData.role === 3
    },
    is_merchant_assist () {
      return this.userData.role === 6
    },
    is_team_lead () {
      return this.userData.role === 7
    },
    is_support () {
      return this.userData.role === 4 || this.userData.role === 5
    },
    is_head_of_support () {
      return this.userData.role === 5
    },
    is_trader () {
      return this.userData.role === 1 || this.userData.role === 2
    },
    is_senior_trader () {
      return this.userData.role === 2
    },
    login (params) {
      return instance.post ('/auth/login/', params)
    },
    async me (params) {
      let response = await instance.get ('/auth/me/', { params })
      if (response.status !== 200) {
        localStorage.removeItem ('userData')
      } else {
        this.userData = {
          ...response.data,
        }
      }

      return { data: this.userData }
    },
    async changePassword (params) {
      const response = await instance.post (`/auth/change-password/`, params)
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
    async setupTwoFA (params) {
      const response = await instance.get (`/auth/2fa-setup/`, { params })
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
    async getNotifications (params) {
      const response = await instance.get (`/auth/notifications/`, { params })
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
    register (params) {
      return instance.post ('/auth/register/', params)
    },
    refresh (params) {
      return instance.post ('/auth/login/refresh/', params)
    },
    logout (params) {
      localStorage.removeItem ('userData')
      localStorage.removeItem ('authData')
      this.$reset ()
    },
    async registerTrader (params) {
      const response = await instance.post (`/auth/register-trader/`, params)
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
    async registerMerchant (params) {
      const response = await instance.post (`/auth/register-merchant/`, params)
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
    async updateUser (params, id) {
      const response = await instance.patch (`/auth/update-user/${id}/`, params)
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
    async registerSupport (params) {
      const response = await instance.post (`/auth/register-support/`, params)
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
