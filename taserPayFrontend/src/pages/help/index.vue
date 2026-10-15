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
          Скрины кабинета: жёлтые номера — куда нажимать. Пополнение USDT — через рабочий чат.
        </p>
      </VCardText>
    </VCard>

    <VCard
      id="list"
      class="mb-6"
    >
      <VCardItem>
        <VCardTitle>1. Payment Details → Create</VCardTitle>
      </VCardItem>
      <VCardText>
        <div class="shot-wrap">
          <img
            src="/help-shots/01-list.png"
            alt="Payment Details"
            class="shot-img"
          >
          <div
            class="pin"
            style="left: 3%; top: 28%;"
          >
            <span class="dot">1</span>
            <span class="lab">Payment Details</span>
          </div>
          <div
            class="pin"
            style="left: 20%; top: 49%;"
          >
            <span class="dot">2</span>
            <span class="lab">+ Create</span>
          </div>
        </div>
      </VCardText>
    </VCard>

    <VCard
      id="form"
      class="mb-6"
    >
      <VCardItem>
        <VCardTitle>2. Форма справа</VCardTitle>
        <VCardSubtitle>Owner → свой банк → KZT → Standard → By Card → Active for Orders In</VCardSubtitle>
      </VCardItem>
      <VCardText>
        <div class="shot-wrap">
          <img
            src="/help-shots/02-form.png"
            alt="Форма создания"
            class="shot-img"
          >
          <div
            class="pin pin-right"
            style="left: 72%; top: 16%;"
          >
            <span class="dot">3</span>
            <span class="lab">Owner</span>
          </div>
          <div
            class="pin pin-right"
            style="left: 72%; top: 40%;"
          >
            <span class="dot">4</span>
            <span class="lab">банк / KZT / Standard / By Card</span>
          </div>
          <div
            class="pin pin-right"
            style="left: 72%; top: 57%;"
          >
            <span class="dot">5</span>
            <span class="lab">Active for Orders In</span>
          </div>
          <div
            class="pin pin-right"
            style="left: 72%; top: 88%;"
          >
            <span class="dot">6</span>
            <span class="lab">Add Payment Detail</span>
          </div>
        </div>
        <VAlert
          class="mt-4"
          type="info"
          variant="tonal"
        >
          Payment System: Elkard, Kompanion, Mbank, Optima, O bank, Bai-Tushum.
        </VAlert>
      </VCardText>
    </VCard>

    <VCard
      id="card"
      class="mb-6"
    >
      <VCardItem>
        <VCardTitle>3. Card Number и Save</VCardTitle>
      </VCardItem>
      <VCardText>
        <div class="shot-wrap mb-4">
          <img
            src="/help-shots/03-card.png"
            alt="Card Number и Save"
            class="shot-img"
          >
          <div
            class="pin pin-right"
            style="left: 72%; top: 72%;"
          >
            <span class="dot">7</span>
            <span class="lab">Card Number</span>
          </div>
          <div
            class="pin pin-right"
            style="left: 72%; top: 90%;"
          >
            <span class="dot">8</span>
            <span class="lab">Save</span>
          </div>
        </div>
        <div class="shot-wrap">
          <img
            src="/help-shots/04-filled.png"
            alt="Заполненная форма"
            class="shot-img"
          >
        </div>
      </VCardText>
    </VCard>

    <VCard
      id="orders"
      class="mb-6"
    >
      <VCardItem>
        <VCardTitle>Заявки — Orders In</VCardTitle>
        <VCardSubtitle>Expired / Money Sent By User / Completed. Frozen — холд по заявке.</VCardSubtitle>
      </VCardItem>
      <VCardText>
        <div class="shot-wrap">
          <img
            src="/help-shots/05-orders.png"
            alt="Список заявок"
            class="shot-img"
          >
          <div
            class="pin"
            style="left: 3%; top: 18%;"
          >
            <span class="dot">1</span>
            <span class="lab">Orders In</span>
          </div>
          <div
            class="pin"
            style="left: 18%; top: 58%;"
          >
            <span class="dot">2</span>
            <span class="lab">Money Sent By User — открыть</span>
          </div>
        </div>
      </VCardText>
    </VCard>

    <VCard
      id="complete"
      class="mb-6"
    >
      <VCardItem>
        <VCardTitle>Закрыть заявку</VCardTitle>
        <VCardSubtitle>Карточка справа → Complete (Double Click)</VCardSubtitle>
      </VCardItem>
      <VCardText>
        <div class="shot-wrap">
          <img
            src="/help-shots/06-order.png"
            alt="Карточка заявки"
            class="shot-img"
          >
          <div
            class="pin pin-right"
            style="left: 72%; top: 12%;"
          >
            <span class="dot">3</span>
            <span class="lab">Money Sent By User</span>
          </div>
          <div
            class="pin pin-right"
            style="left: 72%; top: 88%;"
          >
            <span class="dot">4</span>
            <span class="lab">Complete — два клика</span>
          </div>
        </div>
        <VAlert
          class="mt-4"
          type="warning"
          variant="tonal"
        >
          Не закрывайте, пока не видите зачисление. Спор — в рабочий чат.
        </VAlert>
      </VCardText>
    </VCard>

    <VCard
      id="filters"
      class="mb-6"
    >
      <VCardItem>
        <VCardTitle>Фильтры</VCardTitle>
        <VCardSubtitle>Status = Arbitrage → Search</VCardSubtitle>
      </VCardItem>
      <VCardText>
        <div class="shot-wrap">
          <img
            src="/help-shots/07-filters.png"
            alt="Фильтры"
            class="shot-img"
          >
        </div>
      </VCardText>
    </VCard>

    <VCard
      id="profile"
      class="mb-6"
    >
      <VCardItem>
        <VCardTitle>Профиль</VCardTitle>
        <VCardSubtitle>Email сверху справа → Base Info, пароль, 2FA</VCardSubtitle>
      </VCardItem>
      <VCardText>
        <div class="shot-wrap">
          <img
            src="/help-shots/08-profile.png"
            alt="Профиль"
            class="shot-img"
          >
          <div
            class="pin"
            style="left: 22%; top: 48%;"
          >
            <span class="dot">7</span>
            <span class="lab">Telegram / Phone → Update User</span>
          </div>
          <div
            class="pin"
            style="left: 22%; top: 78%;"
          >
            <span class="dot">8</span>
            <span class="lab">Смена пароля</span>
          </div>
          <div
            class="pin pin-right"
            style="left: 62%; top: 82%;"
          >
            <span class="dot">9</span>
            <span class="lab">2FA Setup</span>
          </div>
        </div>
        <VAlert
          class="mt-4"
          type="success"
          variant="tonal"
        >
          Email и имя не меняйте сами. Потеря доступа — рабочий чат.
        </VAlert>
      </VCardText>
    </VCard>

    <VCard
      id="tx"
      class="mb-6"
    >
      <VCardItem>
        <VCardTitle>Транзакции</VCardTitle>
        <VCardSubtitle>Профиль → Transactions: холд, expire, Complete</VCardSubtitle>
      </VCardItem>
      <VCardText>
        <div class="shot-wrap">
          <img
            src="/help-shots/09-tx.png"
            alt="Транзакции"
            class="shot-img"
          >
        </div>
      </VCardText>
    </VCard>

    <VCard class="mb-6">
      <VCardItem>
        <VCardTitle>Пополнение</VCardTitle>
      </VCardItem>
      <VCardText>
        <VAlert
          type="success"
          variant="tonal"
        >
          Пополнение USDT — через рабочий чат. Не слать на адрес из кабинета без подтверждения суммы, сети и адреса.
        </VAlert>
      </VCardText>
    </VCard>
  </div>
</template>

<style scoped>
.shot-wrap {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.shot-img {
  display: block;
  width: 100%;
  height: auto;
}
.pin {
  position: absolute;
  transform: translate(-8px, -50%);
  display: flex;
  align-items: center;
  gap: 8px;
  pointer-events: none;
  max-width: 46%;
  filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.25));
}
.pin-right {
  flex-direction: row-reverse;
  transform: translate(8px, -50%);
}
.dot {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgb(var(--v-theme-warning));
  color: #1f2937;
  font-weight: 800;
  font-size: 0.85rem;
  display: grid;
  place-items: center;
  outline: 3px solid #fff;
}
.lab {
  background: #111827;
  color: #fff;
  font-size: 0.78rem;
  font-weight: 600;
  padding: 6px 10px;
  border-radius: 8px;
}
</style>
