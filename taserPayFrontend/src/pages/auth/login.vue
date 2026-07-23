<script setup>
import {
  requiredValidator,
} from '@validators'
import { VNodeRenderer } from '@layouts/components/VNodeRenderer'
import { themeConfig } from '@themeConfig'
import { useAuthStore } from "@/stores/useAuthStore"

const snackbar = ref ({
  enabled: false,
  type: 'error',
  message: 'Permission denied!',
})

const form = ref ({
  username: '',
  password: '',
  stay_signed: false,
  code: '',
})

const isLoading = ref (false)
const isPasswordVisible = ref (false)

const router = useRouter ()
const authStore = useAuthStore ()
const refForm = ref ()

const login = async () => {
  const validation = await refForm?.value?.validate ()
  if (!validation.valid) {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: "Проверьте правильность заполнения всех полей!",
    }

    return
  }

  isLoading.value = true
  let response
  try {
    response = await authStore.login (form.value)

    if (!response.data.access) {
      snackbar.value = {
        enabled: true,
        type: 'error',
        message: response.data,
      }
      isLoading.value = false

      return
    }
  } catch (e) {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: e.data,
    }
    isLoading.value = false

    return
  }

  authStore.authData = {
    ...authStore.authData,
    access: `${response.data.access}`,
    refresh: `${response.data.refresh}`,
  }
  response = await authStore.me ({})
  if (response.data.error) {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: response.data.error,
    }
    isLoading.value = false

    return
  }
  authStore.userData = response.data
  snackbar.value = {
    enabled: true,
    type: 'success',
    message: "Successfully Logged In!",
  }
  isLoading.value = false
  setTimeout (
    () => {
      router.push ({ name: authStore.authData.nextUrl })
    },
    1000,
  )
}
</script>

<template>
  <div class="auth-page">
    <VSnackbar
      v-model="snackbar.enabled"
      location="bottom end"
      variant="flat"
      transition="scroll-y-reverse-transition"
      :color="snackbar.type"
    >
      {{ snackbar.message }}
    </VSnackbar>

    <div class="auth-page__card">
      <header class="auth-page__brand">
        <div class="auth-page__logo">
          <VNodeRenderer :nodes="themeConfig.app.logo" />
        </div>
        <h1 class="auth-page__title">
          {{ themeConfig.app.title }}
        </h1>
        <p class="auth-page__subtitle">
          {{ $t('login_view.slogan') }}
        </p>
      </header>

      <VForm
        ref="refForm"
        class="auth-page__form"
        @submit.prevent="login"
      >
        <div class="auth-page__row">
          <UiTextField
            v-model="form.username"
            :label="$t('username')"
            type="text"
            autocomplete="username"
            :rules="[requiredValidator]"
          />

          <UiTextField
            v-model="form.password"
            :label="$t('password')"
            :type="isPasswordVisible ? 'text' : 'password'"
            autocomplete="current-password"
            :rules="[requiredValidator]"
            :append-inner-icon="isPasswordVisible ? 'lucide:eye-off' : 'lucide:eye'"
            @click:append-inner="isPasswordVisible = !isPasswordVisible"
          />

          <UiTextField
            v-model="form.code"
            :label="$t('2fa')"
            type="number"
            autocomplete="one-time-code"
            hint="Optional"
          />
        </div>

        <div class="auth-page__options">
          <VCheckbox
            v-model="form.stay_signed"
            :label="$t('remember_me')"
            density="compact"
            hide-details
          />
        </div>

        <UiButton
          class="auth-page__submit"
          variant="primary"
          block
          type="submit"
          :loading="isLoading"
          :disabled="isLoading"
        >
          {{ $t('login') }}
        </UiButton>
      </VForm>
    </div>
  </div>
</template>

<route lang="yaml">
meta:
  title: Login
  layout: blank
</route>
