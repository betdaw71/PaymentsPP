# Page Override: HeadSupport Dashboard

> Overrides MASTER.md for `HeadSupportDashboard.vue`

## Layout

- Single `ApWorkspace` surface — no nested VCards
- Header: title left, period filter + refresh right
- KPI row: 4 equal `ApMetricCard` components

## KPI Priority (information hierarchy)

1. Total turnover (in + out) — largest number
2. Margin USD
3. Pending withdrawals — warning color if > 0
4. Conversion rate (in) — smaller, secondary

## Charts

| Chart | Type | Notes |
|-------|------|-------|
| Daily turnover | Area, 2 series | In + Out only; margin as third toggle |
| Funnel in/out | Horizontal bar | Stage labels left, count right |
| By PS / currency | Grouped bar | Max 8 categories, scroll if more |

Colors from `chartPalette` in tokens — NOT apex default Vuexy series.

## Tables

- Use `ApDataGrid` with collapsible sections
- Section titles: sentence case, not UPPERCASE
- Exchange rates: last section, collapsed by default

## Empty / Loading

- Skeleton loaders for KPI + chart areas
- Empty state: icon + message + refresh action
