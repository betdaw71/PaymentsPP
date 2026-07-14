import i18n from '@/plugins/i18n/index'

const { t } = i18n.global
export const Skins = {
  Default: 'default',
  Bordered: 'bordered',
}
export const RouteTransitions = {
  Fade: 'app-transition-fade',
  None: 'none',

  // 'Zoom Fade': 'app-transition-zoom-fade',
  // 'Fade Bottom': 'app-transition-fade-bottom',
  // 'Slide Fade': 'app-transition-slide-fade',
  // 'Zoom out': 'app-transition-zoom-out',
}
export const ROLE_MAPPING = {
  "-1": {
    status: t ('roles.banned'),
    chip: { color: 'error' },
  },
  "1": {
    status: t ('roles.trader'),
    chip: { color: 'success' },
  },
  "2": {
    status: t ('roles.senior_trader'),
    chip: { color: 'warning' },
  },
  "3": {
    status: t ('roles.merchant'),
    chip: { color: 'alternative' },
  },
  "4": {
    status: t ('roles.support'),
    chip: { color: 'info' },
  },
  "5": {
    status: t ('roles.head_of_support'),
    chip: { color: 'error' },
  },
  "6": {
    status: t ('roles.merchant_assist'),
    chip: { color: 'warning' },
  },
  "7": {
    status: t ('roles.team_lead'),
    chip: { color: 'success' },
  },
}

export const TRANSACTION_TYPE_MAPPING = {
  "Freeze": {
    text: t ('Freeze'),
    variant: 'info',
    icon: 'tabler-snowflake',
  },
  "Charge": {
    text: t ('Charge'),
    variant: 'warning',
    icon: 'tabler-wallet',
  },
  "Deposit": {
    text: t ('Deposit'),
    variant: 'success',
    icon: 'tabler-cash-banknote',
  },
  "Transfer": {
    text: t ('Transfer'),
    variant: 'warning',
    icon: 'tabler-cash-banknote',
  },
  "Withdrawal": {
    text: t ('Withdrawal'),
    variant: 'error',
    icon: 'tabler-send',
  },
}

export const WITHDRAWAL_STATUS_MAPPING = {
  "0": {
    text: t ('withdrawals.new'),
    variant: 'info',
    icon: 'tabler-new-section',
  },
  "1": {
    text: t ('withdrawals.success'),
    variant: 'success',
    icon: 'tabler-circle-check',
  },
  "2": {
    text: t ('withdrawals.rejected'),
    variant: 'error',
    icon: 'tabler-circle-x',
  },
}

export const PAYMENT_DETAILS_STATUS_MAPPING = {
  "0": {
    text: t ('inactive'),
    variant: 'error',
    icon: 'tabler-new-section',
  },
  "1": {
    text: t ('active'),
    variant: 'success',
    icon: 'tabler-circle-check',
  },
  "2": {
    text: t ('archived'),
    variant: 'secondary',
    icon: 'tabler-circle-x',
  },
  "3": {
    text: t ('blocked_by_support'),
    variant: 'secondary',
    icon: 'tabler-circle-x',
  },
  "4": {
    text: t ('arbitrage_blocked'),
    variant: 'secondary',
    icon: 'tabler-circle-x',
  },
  "5": {
    text: t ('blocked_by_bot'),
    variant: 'secondary',
    icon: 'tabler-circle-x',
  },

  // Add more as needed
}
export const SMS_STATUS_MAPPING = {
  "wrong-state": {
    text: t ('wrong_state'),
    variant: 'error',
    icon: 'tabler-new-section',
  },
  "success": {
    text: t ('success'),
    variant: 'success',
    icon: 'tabler-circle-check',
  },
  "pending": {
    text: t ('pending'),
    variant: 'secondary',
    icon: 'tabler-circle-dot',
  },
  "not-found": {
    text: t ('not_found'),
    variant: 'primary',
    icon: 'tabler-circle-x',
  },
  "red-block": {
    text: t ('red_block'),
    variant: 'error',
    icon: 'tabler-barrier-block',
  },
  "fz-block": {
    text: t ('fz_block'),
    variant: 'warning',
    icon: 'tabler-gavel',
  },
  "compr-block": {
    text: t ('compr_block'),
    variant: 'secondary',
    icon: 'tabler-lock',
  },
}
export const IN_ORDER_STATUS_MAPPING = {
  "New": {
    text: t ('new'),
    variant: 'info',
    icon: 'tabler-circle-dot',
  },
  "Money sent by user": {
    text: t ('money_sent_by_user'),
    variant: 'warning',
    icon: 'tabler-circle-dot',
  },
  "Arbitrage":{
    text: t ('arbitrage'),
    variant: 'alternative',
    icon: 'tabler-circle-dot',
  },
  "Completed":{
    text: t ('completed'),
    variant: 'success',
    icon: 'tabler-circle-dot',
  },
  "Cancelled by support":{
    text: t ('cancelled_by_support'),
    variant: 'error',
    icon: 'tabler-circle-dot',
  },
  "Cannot process":{
    text: t ('cannot_process'),
    variant: 'error',
    icon: 'tabler-circle-dot',
  },
  "Expired": {
    text: t ('expired'),
    variant: 'error',
    icon: 'tabler-circle-dot',
  },
  "Cancelled": {
    text: t ('cancelled'),
    variant: 'error',
    icon: 'tabler-circle-dot',
  },
}

export const OUT_ORDER_STATUS_MAPPING = {
  "New": {
    text: t ('new'),
    variant: 'info',
    icon: 'tabler-circle-dot',
  },
  "Money sent by trader": {
    text: t ('money_sent_by_trader'),
    variant: 'warning',
    icon: 'tabler-circle-dot',
  },
  "Arbitrage":{
    text: t ('arbitrage'),
    variant: 'alternative',
    icon: 'tabler-circle-dot',
  },
  "Completed":{
    text: t ('completed'),
    variant: 'success',
    icon: 'tabler-circle-dot',
  },
  "Cancelled by support":{
    text: t ('cancelled_by_support'),
    variant: 'error',
    icon: 'tabler-circle-dot',
  },
  "Cannot process":{
    text: t ('cannot_process'),
    variant: 'error',
    icon: 'tabler-circle-dot',
  },
  "Expired": {
    text: t ('expired'),
    variant: 'error',
    icon: 'tabler-circle-dot',
  },
  "Cancelled": {
    text: t ('cancelled'),
    variant: 'error',
    icon: 'tabler-circle-dot',
  },
  "Failed": {
    text: t ('failed'),
    variant: 'error',
    icon: 'tabler-circle-dot',
  },
}
