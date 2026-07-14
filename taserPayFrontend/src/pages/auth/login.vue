<script setup>
import {
  confirmedValidator,
  emailValidator,
  passwordValidator,
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
  // email: '',
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
  let validation = await refForm?.value?.validate ()
  if (!validation.valid) {
    snackbar.value = {
      enabled: true,
      type: 'error',
      message: "Проверьте правильность заполнения всех полей!",
    }

    return
  }
  let response
  isLoading.value = true
  try {
    response = await authStore.login (form.value)

    // console.log (response.data)
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
      router.push ({ "name": authStore.authData.nextUrl })
    },
    1000,
  )
}
</script>

<template>
  <div
    class="auth-wrapper  d-flex justify-center align-center pa-md-4"
  >
    <VSnackbar
      v-model="snackbar.enabled"
      location="bottom end"
      variant="flat"
      transition="scroll-y-reverse-transition"
      :color="snackbar.type"
    >
      {{ snackbar.message }}
    </VSnackbar>
    <div class="position-relative">
      <!-- 👉 Top shape -->

      <!-- 👉 Auth Card -->
      <VCard
        class="auth-card pa-4"
        min-width="448"
        max-width="448"
      >
        <VCardItem class="justify-center">
          <template #prepend>
            <div class="d-flex">
              <VNodeRenderer :nodes="themeConfig.app.logo" />
            </div>
          </template>

          <VCardTitle class="font-weight-bold text-h5 py-1">
            {{ themeConfig.app.title }}
          </VCardTitle>
        </VCardItem>

        <VCardText class="pt-1">
          <h5 class="text-h5 font-weight-semibold mb-1">
            {{ $t('login_view.welcome') }}
          </h5>
          <p class="mb-0">
            {{ $t('login_view.slogan') }}
          </p>
        </VCardText>

        <VCardText>
          <VForm
            ref="refForm"
            @submit.prevent="() => {}"
          >
            <VRow>
              <!-- email -->
              <VCol cols="12">
                <VTextField
                  v-model="form.username"
                  :label="$t('username')"
                  type="text"
                  :rules="[requiredValidator]"
                />
              </VCol>

              <!-- password -->
              <VCol cols="12">
                <VTextField
                  v-model="form.password"
                  :label="$t('password')"
                  :type="isPasswordVisible ? 'text' : 'password'"
                  :rules="[requiredValidator]"
                  autocomplete="on"
                  :append-inner-icon="isPasswordVisible ? 'tabler-eye-off' : 'tabler-eye'"
                  @click:append-inner="isPasswordVisible = !isPasswordVisible"
                />
              </VCol>
              <VCol cols="12">
                <VTextField
                  v-model="form.code"
                  :label="$t('2fa')"
                  type="number"
                />

                <!-- remember me checkbox -->
                <div class="d-flex align-center justify-space-between flex-wrap mt-2 mb-4">
                  <VCheckbox
                    v-model="form.stay_signed"
                    :label="$t('remember_me')"
                  />

                  <!--                  <RouterLink -->
                  <!--                    class="text-primary ms-2 mb-1" -->
                  <!--                    :to="{ name: 'auth-forgot' }" -->
                  <!--                  > -->
                  <!--                    Забыли пароль? -->
                  <!--                  </RouterLink> -->
                </div>

                <!-- login button -->
                <VBtn
                  :loading="isLoading"
                  :disabled="isLoading"
                  block
                  type="submit"
                  @click="login"
                >
                  {{ $t('login') }}
                </VBtn>
              </VCol>

              <!-- create account -->
              <!--              <VCol -->
              <!--                cols="12" -->
              <!--                class="text-center text-base" -->
              <!--              > -->
              <!--                <span>Нет аккаунта?</span> -->
              <!--                <RouterLink -->
              <!--                  class="text-primary ms-2" -->
              <!--                  :to="{ name: 'auth-register' }" -->
              <!--                > -->
              <!--                  Зарегистрироваться -->
              <!--                </RouterLink> -->
              <!--              </VCol> -->
            </VRow>
          </VForm>
        </VCardText>
      </VCard>
    </div>
  </div>
</template>

<style lang="scss">
@use "@core/scss/template/pages/page-auth.scss";
</style>

<route lang="yaml">
meta:
title: Login
</route>
