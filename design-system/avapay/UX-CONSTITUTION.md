# AvaPay UX Constitution

> Рабочее пространство для всего рынка процессинга — не кабинет одного пользователя.

## Meta-principle

**Operational Truth Line × Market Workspace**

> Единая линия правды о деньгах — для всех ролей, в каждой теме, в каждом экране.

**Формула:** Деньги видны → Статус ясен → Ответственность понятна → Действие одно и рядом.

---

## 10 principles

1. **Market Workspace** — один язык UI для трейдеров, мерчантов, support; меняются права, не паттерны.
2. **Operational Truth Line** — primary block: сумма → status badge → owner/queue → primary action.
3. **Amount & status first** — ID, UUID, tech fields secondary / copy-on-click.
4. **One list language** — orders, withdrawals, SMS, transactions = одна ops-row.
5. **Master–detail** — список остаётся, детали в drawer справа.
6. **Queue = workplace** — arbitrage, manual check = triage strip с count > 0 alert.
7. **Filters: fast top, deep collapsible** — `ApFilterPanel`, не простыня полей.
8. **Semantic color only** — цвет = процесс (success/warning/error/info), не декор.
9. **Dark mode = peer theme** — полноценная тёмная палитра для смен 24/7.
10. **Trust + micro-states** — audit visible, mask secrets, spinner на кнопке не fullscreen loader.

---

## Component mapping

| Pattern | Component |
|---------|-----------|
| Page surface | `ApWorkspace` |
| Page title | `ApPageHeader` |
| Money KPI strip | `ApTruthStrip` |
| Support queues | `ApQueueStrip` |
| Stable actions | `ApActionZone` |
| Filters | `ApFilterPanel` |
| Tables | `ApDataGrid` |
| Status | `ApStatusBadge` |
| KPI cards | `ApMetricCard` |

---

## Screen checklist

- [ ] Сумма крупнее ID?
- [ ] Статус с иконкой + текстом?
- [ ] Один primary action в зоне действий?
- [ ] Нет дубля nav + tabs?
- [ ] Фильтры collapsible?
- [ ] Dark mode читаем?
- [ ] Sensitive data masked?
