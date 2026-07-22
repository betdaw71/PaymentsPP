<script setup>
import UiButton from '@/components/ui/UiButton.vue'
import UiTextField from '@/components/ui/UiTextField.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiFilterBar from '@/components/ui/UiFilterBar.vue'
import UiFilterPanel from '@/components/ui/UiFilterPanel.vue'

const sections = [
  { id: 'tokens', label: 'Токены', icon: 'tabler-palette' },
  { id: 'buttons', label: 'Кнопки', icon: 'tabler-click' },
  { id: 'inputs', label: 'Инпуты', icon: 'tabler-forms' },
  { id: 'filters', label: 'Фильтры', icon: 'tabler-filter' },
  { id: 'compare', label: 'Было / Стало', icon: 'tabler-columns' },
]

const activeSection = ref('buttons')
const lastAction = ref('—')
const filterExpanded = ref(true)
const filterLoading = ref(false)
const showInputError = ref(false)
const inputDisabled = ref(false)

const statusItems = [
  { title: 'New', value: 'New' },
  { title: 'In Progress', value: 'In Progress' },
  { title: 'Success', value: 'Success' },
  { title: 'Failed', value: 'Failed' },
]

const filters = ref({
  search: '',
  status: null,
  minAmount: '',
  maxAmount: '',
})

const colorTokens = [
  { name: 'Primary', var: '--ui-primary', hint: 'Telegram blue' },
  { name: 'Accent', var: '--ui-accent', hint: 'Grafana orange' },
  { name: 'Success', var: '--ui-success', hint: 'Shopify green' },
  { name: 'Surface', var: '--ui-surface', hint: 'Cards' },
  { name: 'Background', var: '--ui-bg', hint: 'Page canvas' },
  { name: 'Border', var: '--ui-border', hint: 'Dividers' },
]

const activeFilterCount = computed(() => {
  let n = 0
  if (filters.value.search) n++
  if (filters.value.status) n++
  if (filters.value.minAmount) n++
  if (filters.value.maxAmount) n++
  return n
})

const filtersPreview = computed(() => JSON.stringify(filters.value, null, 2))

const buttonRows = [
  { variant: 'default', label: 'Default', hint: 'Shopify secondary — bordered' },
  { variant: 'primary', label: 'Primary', hint: 'Telegram blue — главный CTA' },
  { variant: 'accent', label: 'Accent', hint: 'Grafana orange — highlight' },
  { variant: 'active', label: 'Active', hint: 'Selected tab / toggle' },
  { variant: 'ghost', label: 'Ghost', hint: 'Tertiary / link action' },
  { variant: 'danger', label: 'Danger', hint: 'Destructive' },
]

const scrollTo = id => {
  activeSection.value = id
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const applyFilters = () => {
  filterLoading.value = true
  lastAction.value = `apply @ ${new Date().toLocaleTimeString()}`
  setTimeout(() => { filterLoading.value = false }, 500)
}

const resetFilters = () => {
  filters.value = { search: '', status: null, minAmount: '', maxAmount: '' }
  lastAction.value = `reset @ ${new Date().toLocaleTimeString()}`
}
</script>

<template>
  <div class="ui-lab">
    <header class="ui-lab__header">
      <div>
        <div class="ui-lab__eyebrow">
          AvaPay Design Lab
        </div>
        <h1 class="ui-lab__title">
          Telegram · Grafana · Shopify
        </h1>
        <p class="ui-lab__subtitle">
          Telegram — чистые flat-кнопки и воздух. Grafana — плотные панели и ops-акцент.
          Shopify Polaris — системные инпуты и footer действий.
        </p>
        <div class="ui-lab__pill-row mt-3">
          <span class="ui-lab__pill ui-lab__pill--tg">Telegram</span>
          <span class="ui-lab__pill ui-lab__pill--gf">Grafana</span>
          <span class="ui-lab__pill ui-lab__pill--sh">Shopify</span>
        </div>
      </div>
      <VChip
        variant="outlined"
        size="small"
        prepend-icon="tabler-route"
      >
        /dev/ui-kit
      </VChip>
    </header>

    <div class="ui-lab__body">
      <nav class="ui-lab__nav">
        <button
          v-for="item in sections"
          :key="item.id"
          type="button"
          class="ui-lab__nav-item"
          :class="{ 'ui-lab__nav-item--active': activeSection === item.id }"
          @click="scrollTo(item.id)"
        >
          <VIcon
            :icon="item.icon"
            size="16"
          />
          {{ item.label }}
        </button>
      </nav>

      <main class="ui-lab__main">
        <!-- TOKENS -->
        <section
          id="tokens"
          class="ui-lab__section"
        >
          <div class="ui-lab__section-head">
            <h2>Цветовые токены</h2>
            <p>База дизайн-системы — правим здесь, страницы не трогаем.</p>
          </div>
          <div class="ui-lab__swatch-grid">
            <div
              v-for="token in colorTokens"
              :key="token.var"
              class="ui-lab__swatch"
            >
              <div
                class="ui-lab__swatch-color"
                :style="{ background: `var(${token.var})` }"
              />
              <div class="ui-lab__swatch-meta">
                <strong>{{ token.name }}</strong>
                {{ token.hint }}<br>{{ token.var }}
              </div>
            </div>
          </div>
        </section>

        <!-- BUTTONS -->
        <section
          id="buttons"
          class="ui-lab__section"
        >
          <div class="ui-lab__section-head">
            <h2>Кнопки</h2>
            <p>Flat primary (TG), bordered secondary (Shopify), orange accent (Grafana).</p>
          </div>

          <div class="ui-lab__matrix">
            <div
              v-for="row in buttonRows"
              :key="row.variant"
              class="ui-lab__matrix-row"
            >
              <div class="ui-lab__matrix-label">
                <strong>{{ row.label }}</strong>
                <span>{{ row.hint }}</span>
              </div>
              <div class="ui-lab__matrix-cells">
                <UiButton :variant="row.variant">
                  {{ row.label }}
                </UiButton>
                <UiButton
                  :variant="row.variant"
                  size="small"
                >
                  Small
                </UiButton>
                <UiButton
                  :variant="row.variant"
                  loading
                >
                  Loading
                </UiButton>
                <UiButton
                  :variant="row.variant"
                  disabled
                >
                  Disabled
                </UiButton>
              </div>
            </div>
          </div>

          <div class="ui-lab__row-actions">
            <span class="text-caption text-medium-emphasis">Toolbar:</span>
            <UiButton variant="ghost">
              Сбросить
            </UiButton>
            <UiButton variant="primary">
              Применить
            </UiButton>
            <UiButton variant="accent">
              Экспорт
            </UiButton>
            <UiButton variant="danger">
              Отклонить
            </UiButton>
          </div>
        </section>

        <!-- INPUTS -->
        <section
          id="inputs"
          class="ui-lab__section"
        >
          <div class="ui-lab__section-head">
            <h2>Инпуты</h2>
            <p>Shopify Polaris: label сверху, border, focus ring. ID — monospace.</p>
          </div>

          <div class="ui-lab__toggles mb-4">
            <VSwitch
              v-model="showInputError"
              label="Error state"
              color="primary"
              hide-details
              density="compact"
            />
            <VSwitch
              v-model="inputDisabled"
              label="Disabled"
              color="primary"
              hide-details
              density="compact"
            />
          </div>

          <VRow>
            <VCol
              cols="12"
              md="4"
            >
              <UiTextField
                v-model="filters.search"
                label="Order ID"
                placeholder="22652802379"
                :disabled="inputDisabled"
                :error="showInputError"
                :error-messages="showInputError ? 'Invalid format' : undefined"
                clearable
                class="ui-field--mono"
              />
            </VCol>
            <VCol
              cols="12"
              md="4"
            >
              <UiTextField
                v-model="filters.minAmount"
                label="Min amount"
                type="number"
                placeholder="1000"
                :disabled="inputDisabled"
              />
            </VCol>
            <VCol
              cols="12"
              md="4"
            >
              <UiSelect
                v-model="filters.status"
                label="Status"
                :items="statusItems"
                item-title="title"
                item-value="value"
                :disabled="inputDisabled"
                clearable
              />
            </VCol>
          </VRow>
        </section>

        <!-- FILTERS -->
        <section
          id="filters"
          class="ui-lab__section"
        >
          <div class="ui-lab__section-head">
            <h2>Фильтры</h2>
            <p>Grafana panel header + Shopify action footer + compact chip bar.</p>
          </div>

          <UiFilterPanel
            v-model:expanded="filterExpanded"
            :active-count="activeFilterCount"
            :loading="filterLoading"
            @apply="applyFilters"
            @reset="resetFilters"
          >
            <VRow dense>
              <VCol
                cols="12"
                md="4"
              >
                <UiTextField
                  v-model="filters.search"
                  label="ID заявки"
                  clearable
                />
              </VCol>
              <VCol
                cols="12"
                md="4"
              >
                <UiSelect
                  v-model="filters.status"
                  label="Статус"
                  :items="statusItems"
                  item-title="title"
                  item-value="value"
                  clearable
                />
              </VCol>
              <VCol
                cols="6"
                md="2"
              >
                <UiTextField
                  v-model="filters.minAmount"
                  label="Min"
                  type="number"
                />
              </VCol>
              <VCol
                cols="6"
                md="2"
              >
                <UiTextField
                  v-model="filters.maxAmount"
                  label="Max"
                  type="number"
                />
              </VCol>
            </VRow>
          </UiFilterPanel>

          <UiFilterBar
            class="mt-3"
            :active-count="activeFilterCount"
            :loading="filterLoading"
            @apply="applyFilters"
            @reset="resetFilters"
          >
            <span
              v-if="filters.status"
              class="ui-chip ui-chip--accent"
            >
              {{ filters.status }}
            </span>
            <span
              v-if="filters.search"
              class="ui-chip"
            >
              ID: {{ filters.search }}
            </span>
          </UiFilterBar>

          <div class="mt-3">
            <pre class="ui-lab__code">{{ filtersPreview }}</pre>
            <div class="text-caption text-medium-emphasis mt-2">
              {{ lastAction }}
            </div>
          </div>
        </section>

        <!-- COMPARE -->
        <section
          id="compare"
          class="ui-lab__section"
        >
          <div class="ui-lab__section-head">
            <h2>Было / Стало</h2>
            <p>Legacy Vuetify vs новая система.</p>
          </div>

          <div class="ui-lab__compare">
            <div class="ui-lab__compare-col">
              <div class="ui-lab__compare-title">
                Legacy
              </div>
              <div class="d-flex flex-wrap gap-2">
                <VBtn
                  variant="outlined"
                  size="small"
                >
                  Outlined
                </VBtn>
                <VBtn
                  color="primary"
                  size="small"
                >
                  Primary
                </VBtn>
                <VBtn
                  color="primary"
                  variant="tonal"
                  size="small"
                >
                  Tonal
                </VBtn>
                <VBtn
                  variant="text"
                  size="small"
                >
                  Text
                </VBtn>
              </div>
            </div>
            <div class="ui-lab__compare-col ui-lab__compare-col--new">
              <div class="ui-lab__compare-title">
                UI Kit
              </div>
              <div class="d-flex flex-wrap gap-2">
                <UiButton
                  variant="default"
                  size="small"
                >
                  Default
                </UiButton>
                <UiButton
                  variant="primary"
                  size="small"
                >
                  Primary
                </UiButton>
                <UiButton
                  variant="active"
                  size="small"
                >
                  Active
                </UiButton>
                <UiButton
                  variant="ghost"
                  size="small"
                >
                  Ghost
                </UiButton>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<route lang="yaml">
meta:
  layout: blank
</route>
