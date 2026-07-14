import axiosInstance from "./api"
import EventBus from "@/services/EventBus"

const setup = store => {
  axiosInstance.interceptors.request.use (
    config => {
      const token = store.authData.access
      if (token) {
        config.headers["Authorization"] = `${import.meta.env.VITE_AUTHORIZATION_HEADER ? import.meta.env.VITE_AUTHORIZATION_HEADER : "Bearer"} ${token}`

        // config.headers["Authorization"] = `Bearer ${token}`;
      }

      return config
    },
    error => {
      return Promise.reject (error)
    },
  )
  axiosInstance.interceptors.response.use(
    response => {
      const contentType = response.headers['content-type']
      if (contentType && contentType.includes('application/json')) {
        if (response.data && typeof response.data === 'string')
          response.data = JSON.parse(response.data)
      }

      return response
    },
    error => {
      return Promise.reject(error)
    },
  )
  axiosInstance.interceptors.response.use(
    response => {
      if (response.status > 500) {
        store.authData.maintenance = true
        EventBus.dispatch('maintenance_enabled')
      } else if (response.status < 500 && store.authData.maintenance) {
        store.authData.maintenance = false
        EventBus.dispatch('maintenance_disabled')
      }

      return response
    },
    error => {
      return Promise.reject(error)
    },
  )
  axiosInstance.interceptors.response.use (
    res => {
      const originalConfig = res?.config
      if (!originalConfig.url.includes ("refresh")

        // && !originalConfig.url.includes ("xlogin")
        // && !originalConfig.url.includes ("register")
        && res) {
        if (res.status === 401 && !originalConfig._retry) {
          if(originalConfig.url.includes('login')){
            return Promise.reject (res)
          }
          originalConfig._retry = true
          console.log({ originalConfig })

          return store.refresh ({
            refresh: store.authData.refresh,
          })
            .then (
              response => {
                const { access } = response.data
                if (access !== null && access !== undefined) {
                  store.authData.access = access
                  console.log({ access })

                  return axiosInstance.request ({
                    ...originalConfig,
                    headers: {
                      ...originalConfig.headers,
                      Authorization: `${import.meta.env.VITE_AUTHORIZATION_HEADER} ${access}`,
                    },
                    responseType: 'json',
                  })
                }
                store.logout ()
                EventBus.dispatch ("logout")

                return Promise.reject ()
              },
              error => {
                store.logout ()
                EventBus.dispatch ("logout")

                return Promise.reject (error)
              },
            )
        }
      }

      return res
    },
    async err => {
      const originalConfig = err.config
      if (originalConfig.url.includes ("refresh") && err.response) {
        if (err.response.status === 401 && !originalConfig._retry) {
          originalConfig._retry = true

          return store.refresh ({
            refresh: store.authData.refresh,
          })
            .then (
              response => {
                const { access } = response.data
                if (access !== null) {
                  store.authData.access = access

                  return axiosInstance.request (originalConfig)
                }
                store.logout ()

                return Promise.reject ()
              },
              error => {
                store.logout ()

                // store.dispatch ('auth/logout');
                // TokenService.removeUser ();
                // EventBus.dispatch ("logout");
                return Promise.reject (error)
              },
            )
        }
      }

      return Promise.reject (err)
    },
  )
}

export default setup
