<script setup>
</script>

<template>
  <div>
    <VCard class="mb-6">
      <VCardText>
        <h4 class="text-h4 mb-2">
          {{ $t('knowledge_base') }}
        </h4>
        <p class="text-body-1 mb-0">
          Как завести карту, что менять в профиле и как пополнять баланс. Жёлтая подсветка — куда нажимать в кабинете.
        </p>
      </VCardText>
    </VCard>

    <VRow>
      <VCol
        cols="12"
        md="8"
      >
        <VCard
          id="requisites"
          class="mb-6"
        >
          <VCardItem>
            <VCardTitle>Как добавить реквизит</VCardTitle>
            <VCardSubtitle>Payment Details → Create → банк → KZT → Standard → By card</VCardSubtitle>
          </VCardItem>
          <VCardText>
            <VTimeline
              density="compact"
              align="start"
              line-inset="8"
            >
              <VTimelineItem
                dot-color="primary"
                size="small"
              >
                <div class="font-weight-medium mb-1">
                  1. Откройте раздел Payment Details
                </div>
                <div class="text-medium-emphasis">
                  Меню слева: «Реквизиты».
                </div>
                <VSheet
                  class="mt-3 pa-3 rounded-lg"
                  color="grey-lighten-4"
                >
                  <div class="d-flex align-center justify-space-between">
                    <span class="font-weight-medium">💳 Payment Details</span>
                    <VChip
                      size="small"
                      color="warning"
                      variant="tonal"
                    >
                      меню слева
                    </VChip>
                  </div>
                </VSheet>
              </VTimelineItem>

              <VTimelineItem
                dot-color="primary"
                size="small"
              >
                <div class="font-weight-medium mb-1">
                  2. Нажмите Create
                </div>
                <VSheet
                  class="mt-3 pa-3 rounded-lg"
                  color="grey-lighten-4"
                >
                  <div class="d-flex align-center justify-space-between">
                    <span>Payment Details</span>
                    <VBtn
                      color="primary"
                      size="small"
                      prepend-icon="tabler-plus"
                      class="help-hit"
                    >
                      {{ $t('create') }}
                    </VBtn>
                  </div>
                  <div class="text-caption mt-2 text-warning">
                    Справа откроется форма создания.
                  </div>
                </VSheet>
              </VTimelineItem>

              <VTimelineItem
                dot-color="primary"
                size="small"
              >
                <div class="font-weight-medium mb-1">
                  3. Заполните поля
                </div>
                <VSheet
                  class="mt-3 pa-4 rounded-lg"
                  color="grey-lighten-4"
                >
                  <div class="help-field help-hit mb-3">
                    <div class="text-caption text-medium-emphasis">
                      Owner / имя владельца
                    </div>
                    <div class="font-weight-medium">
                      ФИО как на карте
                    </div>
                  </div>
                  <div class="help-field help-hit mb-3">
                    <div class="text-caption text-medium-emphasis">
                      Payment system
                    </div>
                    <div class="font-weight-medium">
                      ваш банк из списка (не C2CKZT)
                    </div>
                  </div>
                  <div class="help-field help-hit mb-3">
                    <div class="text-caption text-medium-emphasis">
                      Currency
                    </div>
                    <div class="font-weight-medium">
                      Казахские тенге (KZT)
                    </div>
                  </div>
                  <div class="help-field help-hit mb-3">
                    <div class="text-caption text-medium-emphasis">
                      Allowed traffic
                    </div>
                    <div class="font-weight-medium">
                      Standard
                    </div>
                  </div>
                  <div class="help-field help-hit mb-3">
                    <div class="text-caption text-medium-emphasis">
                      Work type
                    </div>
                    <div class="font-weight-medium">
                      By card
                    </div>
                  </div>
                  <div class="help-field help-hit mb-3">
                    <div class="text-caption text-medium-emphasis">
                      Active for Orders In
                    </div>
                    <div class="font-weight-medium">
                      ☑ включено
                    </div>
                  </div>
                  <div class="help-field">
                    <div class="text-caption text-medium-emphasis">
                      Лимиты in orders
                    </div>
                    <div class="font-weight-medium">
                      по необходимости
                    </div>
                  </div>
                </VSheet>
              </VTimelineItem>

              <VTimelineItem
                dot-color="success"
                size="small"
              >
                <div class="font-weight-medium mb-1">
                  4. Номер карты и сохранить
                </div>
                <VSheet
                  class="mt-3 pa-4 rounded-lg"
                  color="grey-lighten-4"
                >
                  <VBtn
                    color="primary"
                    class="help-hit mb-3"
                    block
                  >
                    Add payment details
                  </VBtn>
                  <div class="help-field help-hit mb-3">
                    <div class="text-caption text-medium-emphasis">
                      Card number
                    </div>
                    <div class="font-weight-medium">
                      16 цифр карты
                    </div>
                  </div>
                  <VBtn
                    color="success"
                    variant="tonal"
                    block
                  >
                    Сохранить
                  </VBtn>
                </VSheet>
              </VTimelineItem>
            </VTimeline>

            <VBtn
              class="mt-4"
              color="primary"
              to="/payment/details"
              prepend-icon="tabler-credit-card"
            >
              Открыть Payment Details
            </VBtn>
          </VCardText>
        </VCard>
      </VCol>

      <VCol
        cols="12"
        md="4"
      >
        <VCard class="mb-6">
          <VCardItem>
            <VCardTitle>Какой банк выбрать</VCardTitle>
          </VCardItem>
          <VCardText>
            <p class="text-body-2 mb-3">
              Мерчант шлёт C2CKZT. Вы выбираете банк — клиент увидит его в поле bank.
            </p>
            <div class="d-flex flex-wrap gap-2">
              <VChip
                v-for="bank in ['Elkard', 'Kompanion', 'Mbank', 'Optima', 'O bank', 'Bai-Tushum']"
                :key="bank"
                color="primary"
                variant="tonal"
                size="small"
              >
                {{ bank }}
              </VChip>
            </div>
            <VAlert
              class="mt-4"
              type="warning"
              variant="tonal"
            >
              Не выбирайте C2CKZT — иначе банк у мерчанта будет пустой.
            </VAlert>
          </VCardText>
        </VCard>

        <VCard
          id="profile"
          class="mb-6"
        >
          <VCardItem>
            <VCardTitle>Профиль</VCardTitle>
          </VCardItem>
          <VCardText>
            <p class="text-body-2">
              В правом верхнем углу — ваш email. Оттуда выход из аккаунта.
            </p>
            <VAlert
              type="success"
              variant="tonal"
              class="mt-2"
            >
              Смена почты, пароля, 2FA, телефона и данных профиля — только через рабочий чат. В кабинете эти поля сами не редактируются.
            </VAlert>
          </VCardText>
        </VCard>

        <VCard
          id="deposit"
          class="mb-6"
        >
          <VCardItem>
            <VCardTitle>Пополнение баланса</VCardTitle>
          </VCardItem>
          <VCardText>
            <VAlert
              type="success"
              variant="tonal"
            >
              Пополнение USDT производится через рабочий чат. Не переводите средства на адрес из кабинета, пока сумма, сеть и адрес не подтверждены в чате.
            </VAlert>
            <p class="text-body-2 mt-3 mb-0">
              Вывод — тоже через рабочий чат, если иное не согласовано с командой.
            </p>
          </VCardText>
        </VCard>

        <VCard id="chat">
          <VCardItem>
            <VCardTitle>Рабочий чат</VCardTitle>
          </VCardItem>
          <VCardText>
            <ul class="text-body-2 ps-4 mb-0">
              <li>пополнение и вывод USDT</li>
              <li>правки профиля</li>
              <li>новые банки / лимиты / блокировки карт</li>
              <li>спорные заявки</li>
            </ul>
          </VCardText>
        </VCard>
      </VCol>
    </VRow>
  </div>
</template>

<style scoped>
.help-hit {
  outline: 2px solid rgb(var(--v-theme-warning));
  box-shadow: 0 0 0 6px rgba(var(--v-theme-warning), 0.18);
}
.help-field {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  padding: 10px 12px;
}
</style>
