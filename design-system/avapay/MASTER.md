# AvaPay Design System — Master

> Page overrides: `design-system/avapay/pages/[page].md`

**Project:** AvaPay — payment operations platform (traders, merchants, support)  
**Stack:** Vue 3 + Vuetify 3  
**Goal:** Visually, structurally, and informationally distinct from Vuexy/TitanPay template

---

## Design Direction (corrected from auto-gen)

Auto tool suggested dark OLED + gold. **Rejected for v1** — ops team works 8+ hours; primary mode is **light**, dark is optional toggle.

### Color Palette

| Role | Hex | Vuetify key | Notes |
|------|-----|-------------|-------|
| Primary | `#0E7490` | primary | Teal — trust, fintech, NOT Vuexy purple |
| Primary dark | `#0C6378` | — | Hover/active |
| Accent | `#6366F1` | alternative | Actions, links — indigo not `#7367F0` |
| Success | `#059669` | success | Completed, available balance |
| Warning | `#D97706` | warning | Pending, arbitrage |
| Error | `#DC2626` | error | Failed, blocked |
| Info | `#0284C7` | info | Neutral status |
| Background | `#F1F5F9` | background | Slate-100, not `#F8F7FA` |
| Surface | `#FFFFFF` | surface | Cards |
| Text | `#0F172A` | on-surface | Slate-900 |
| Muted | `#64748B` | — | Labels, captions |
| Border | `#E2E8F0` | — | Tables, inputs |

### Typography

- **Font:** IBM Plex Sans (headings + body) — financial/trust mood per ui-ux-pro-max
- **Scale:** 12 / 13 / 14 / 16 / 20 / 24 / 32
- **Weights:** 400 body, 500 labels, 600 headings, 700 KPI numbers

### Shape & Depth

- **Skin:** Default (flat) — NO Vuexy `Bordered`
- **Radius:** 8px inputs, 12px cards, 6px chips
- **Shadow:** subtle only — `0 1px 3px rgba(15,23,42,.08)` on cards
- **NO** nested card-in-card pattern

### Icons

- Keep Tabler (already integrated) but **change icon choices** per section — avoid Vuexy defaults (`tabler-chart-dots-3`, `tabler-circle` nav bullets)
- Fixed 20px inline, 24px section headers

---

## Component Replacements (Vuexy → AvaPay)

| Vuexy pattern | AvaPay replacement |
|---------------|-------------------|
| `VCard > VAvatar(50) + title > inner VCard` | `ApWorkspace` — single surface, header strip |
| `invoice-list-table` | `ApDataGrid` — sticky header, zebra optional, row actions column |
| `v-tabs-pill` in profile | Role sidebar or top segment control |
| `auth-card` centered | Split auth — brand panel + form panel |
| Vuexy chart colors | Token-based palette from chartPalette |
| `VChip label` everywhere | `ApStatusBadge` — icon + text, consistent sizes |
| Drawer for everything | Inline expand rows + drawer only for complex edit |

---

## Layout Shell

```
┌─────────────────────────────────────────────────────────┐
│ TopBar: logo · global search · balance widget · user   │
├──────────┬──────────────────────────────────────────────┤
│ SideNav  │  PageHeader: title · breadcrumbs · actions  │
│ (compact)│  ─────────────────────────────────────────  │
│  icons + │  FilterBar (collapsible on mobile)          │
│  labels  │  ContentArea                                 │
│          │  Footer minimal                              │
└──────────┴──────────────────────────────────────────────┘
```

- Side nav: **compact** (icon + label, 240px), grouped by domain not flat list
- Top bar: role context (trader balance / merchant balance) always visible
- Remove floating Vuexy vertical nav blur aesthetic

---

## Navigation IA (structural)

**Current:** Orders in nav, profile/admin hidden in user dropdown + tabs  
**Target:**

| Group | Items |
|-------|-------|
| Operations | Orders In, Orders Out, SMS |
| Assets | Payment Details, Balances |
| People | Team (role-gated) |
| Finance | Transactions, Withdrawals |
| Admin | Users, Rates, Settings (head support only) |
| Analytics | Dashboard (head support only) |

Profile page (`user/index`) → **split into nav routes**, not 7 tabs in one page.

---

## Information Architecture (informational)

### Orders list
- **Primary column:** amount + currency (large), not UUID
- **Secondary:** status badge, payment system, time ago
- **Tertiary:** IDs copy-on-click in overflow menu
- **Filters:** sticky bar — status, PS, date range, amount range
- **Mobile:** card layout, not horizontal scroll table

### Dashboard (head support)
- **Row 1:** 4 KPI cards — turnover in/out, margin, pending withdrawals
- **Row 2:** alert queue strip (arbitrage, manual check) — red only when > 0
- **Row 3:** daily chart (area, 2 series max visible)
- **Row 4:** funnel horizontal bars (not duplicate titles)
- **Row 5:** breakdown tables — collapsible sections, default collapsed on mobile

### Transactions / Withdrawals
- Unified `ApDataGrid` config per entity type
- Bulk actions bar when rows selected
- Export button in page header, not buried

### Auth
- Security cues: 2FA field grouped, lock icon, no Vuexy decorative shapes

---

## Anti-Patterns (Do NOT)

- Vuexy purple `#7367F0`, green `#28C76F`, cyan `#00CFE8`
- Bordered skin, double-card nesting
- UPPERCASE table headers via `.toUpperCase()` in template
- Demo components: BuyNow, Customizer, ReferAndEarn, invoice routes
- Tab overload (5+ tabs on one page)
- Emoji icons

---

## Implementation Batches (no micro-approval)

| Batch | Scope | Files touched |
|-------|-------|---------------|
| **B1 Foundation** | tokens, theme, fonts, brand scss, 6 base components | theme.js, themeConfig, styles/, components/ap/ |
| **B2 Shell** | layout, nav IA, top bar | layouts/, navigation/, DefaultLayout* |
| **B3 Auth** | login, register, forgot | pages/auth/ |
| **B4 Operations** | orders in/out, payment details, sms | pages/orders/, payment/, sms/ |
| **B5 Profile split** | break user/index tabs into routes or unified views | pages/user/, views/user/ |
| **B6 Role views** | consolidate 7 folders → shared grid + config | views/user/* |
| **B7 Cleanup** | delete Vuexy demo artifacts | @core demo, components/dialogs demo |

---

## Pre-Delivery Checklist

- [ ] Contrast 4.5:1 on light mode
- [ ] cursor-pointer on interactive elements
- [ ] Transitions 150–300ms
- [ ] Responsive: 375, 768, 1024, 1440
- [ ] No horizontal scroll on mobile tables (card fallback)
- [ ] Focus states visible
- [ ] Status not color-only (icon + text)
