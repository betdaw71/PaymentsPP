import { isToday } from './index'
import DOMPurify from "dompurify"
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

import i18n from '@/plugins/i18n/index'
import {
  IN_ORDER_STATUS_MAPPING, OUT_ORDER_STATUS_MAPPING,
  PAYMENT_DETAILS_STATUS_MAPPING,
  ROLE_MAPPING, SMS_STATUS_MAPPING,
  TRANSACTION_TYPE_MAPPING,
  WITHDRAWAL_STATUS_MAPPING,
} from "@core/enums"

const { t } = i18n.global

dayjs.extend (relativeTime)

export const formatDateBefore = dateString => {

  const currentDate = dayjs () // Assuming the current date and time is now
  const targetDate = dayjs (dateString)

  const diffInYears = currentDate.diff (targetDate, 'year')
  const diffInDays = currentDate.diff (targetDate, 'day')
  const diffInHours = currentDate.diff (targetDate, 'hour')
  const diffInMinutes = currentDate.diff (targetDate, 'minute')
  const diffInSeconds = currentDate.diff (targetDate, 'second')

  if (diffInDays > 0) {
    return targetDate.format ("MMM D") + (diffInYears > 0 ? targetDate.format (" YYYY") : "")
  } else if (diffInHours > 0) {
    return `${diffInHours > 1 ? diffInHours.toString () + ' часов' : 'Час'} назад`
  } else if (diffInMinutes > 0) {
    return `${diffInMinutes > 1 ? diffInMinutes.toString () + ' минут' : 'Минуту'} назад`
  } else {
    return `${diffInSeconds > 1 ? diffInSeconds.toString () + ' секунд' : 'Секунду'} назад`
  }
}
export const splitArrayIntoParts = (arr, numParts) => {
  const len = arr.length
  const chunkSize = Math.ceil (len / numParts) // Round up to ensure each chunk has at least 1 element
  const result = []

  for (let i = 0; i < len; i += chunkSize) {
    result.push (arr.slice (i, i + chunkSize))
  }

  return result
}

export const avatarText = value => {
  if (!value)
    return ''
  const nameArray = value.split (' ')

  return nameArray.map (word => word.charAt (0).toUpperCase ()).join ('')
}

// TODO: Try to implement this: https://twitter.com/fireship_dev/status/1565424801216311297
export const kFormatter = num => {
  const regex = /\B(?=(\d{3})+(?!\d))/g

  return Math.abs (num) > 9999 ? `${Math.sign (num) * +((Math.abs (num) / 1000).toFixed (1))}k` : Math.abs (num).toFixed (0).replace (regex, ',')
}

/**
 * Format and return date in Humanize format
 * Intl docs: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/format
 * Intl Constructor: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/DateTimeFormat
 * @param {String} value date to format
 * @param {Intl.DateTimeFormatOptions} formatting Intl object to format with
 */
export const formatDate = (value, formatting = { month: 'short', day: 'numeric', year: 'numeric' }) => {
  if (!value)
    return value

  return new Intl.DateTimeFormat ('en-US', formatting).format (new Date (value))
}

/**
 * Return short human friendly month representation of date
 * Can also convert date to only time if date is of today (Better UX)
 * @param {String} value date to format
 * @param {Boolean} toTimeForCurrentDay Shall convert to time if day is today/current
 */
export const formatDateToMonthShort = (value, toTimeForCurrentDay = true) => {
  const date = new Date (value)
  let formatting = { month: 'short', day: 'numeric' }
  if (toTimeForCurrentDay && isToday (date))
    formatting = { hour: 'numeric', minute: 'numeric' }

  return new Intl.DateTimeFormat ('en-US', formatting).format (new Date (value))
}
export const prefixWithPlus = value => value > 0 ? `+${value}` : value

export const toDays = (timestamp, delta = false) => {
  const now = Date.now () / 1000
  const difference = (!delta) ? (timestamp - now) : timestamp

  return parseInt (difference / (24 * 60 * 60))
}
export const toMonths = timestamp => {
  return toDays (timestamp / 30, true)
}
export const formatTimestamp = timestamp => {
  const options = { month: 'short', day: 'numeric', year: 'numeric' }

  return new Date (timestamp * 1000).toLocaleDateString ('en-US', options)
}
export const roundToNDigits = (number, n) => {
  const factor = 10 ** n

  return Math.ceil (number * factor) / factor
}

export const capitalize = s => (s && s[0].toUpperCase () + s.slice (1).toLowerCase ()) || ""

export const purify = text => {
  return DOMPurify.sanitize (text)
}
export const formatUUID = uuid => {
  if (!uuid)
    return ''
  
  return `${uuid.split ('-').at (-1)}`
}

export const resolveRole = roleId => {
  const key = roleId.toString ()

  return ROLE_MAPPING[key] || {
    status: t ('roles.anonymous'),
    chip: { color: 'info' },
  }
}

export const resolveTransactionTypeVariantAndIcon = status => {
  const key = status.toString ()

  return TRANSACTION_TYPE_MAPPING[key] || {
    text: t (key),
    variant: 'secondary',
    icon: 'tabler-x',
  }
}

export const resolveWithdrawalStatusVariantAndIcon = status => {
  const key = status.toString ()

  return WITHDRAWAL_STATUS_MAPPING[key] || {
    text: t ('withdrawals.pending'),
    variant: 'secondary',
    icon: 'tabler-x',
  }
}

export const resolvePaymentDetailsStatusVariantAndIcon = status => {
  const key = status.toString ()

  return PAYMENT_DETAILS_STATUS_MAPPING[key] || {
    text: t ('unknown'),
    variant: 'secondary',
    icon: 'tabler-x',
  }
}
export const resolveSmsStatusVariantAndIcon = status => {
  const key = status.toString ()

  return SMS_STATUS_MAPPING[key] || {
    text: t ('unknown'),
    variant: 'secondary',
    icon: 'tabler-x',
  }
}

export const resolveOrderInStatusVariantAndIcon = status => {
  const key = status.toString ()

  return IN_ORDER_STATUS_MAPPING[key] || {
    text: key,
    variant: 'secondary',
    icon: 'tabler-circle-dot',
  }
}

export const resolveOrderOutStatusVariantAndIcon = status => {
  const key = status.toString ()

  return OUT_ORDER_STATUS_MAPPING[key] || {
    text: key,
    variant: 'secondary',
    icon: 'tabler-circle-dot',
  }
}

export const formatTimeDelta = (startTime, endTime) => {
  const timeDelta = (endTime - startTime) / 1000
  const hours = Math.floor (timeDelta / 3600)
  const minutes = Math.floor ((timeDelta % 3600) / 60)
  const seconds = Math.floor (timeDelta % 60)
  const formattedHours = String (hours).padStart (2, '0')
  const formattedMinutes = String (minutes).padStart (2, '0')

  // const formattedSeconds = String(seconds).padStart(2, '0')

  return `${formattedHours}:${formattedMinutes}`
}
export const formatTimeDeltaSeconds = (startTime, endTime) => {
  const timeDelta = (endTime - startTime) / 1000
  const hours = Math.floor (timeDelta / 3600)
  const minutes = Math.floor ((timeDelta % 3600) / 60)
  const seconds = Math.floor (timeDelta % 60)
  const formattedHours = String (hours).padStart (2, '0')
  const formattedMinutes = String (minutes).padStart (2, '0')
  const formattedSeconds = String (seconds).padStart (2, '0')
  if (hours === 0) return `${formattedMinutes}:${formattedSeconds}`

  return `${formattedHours}:${formattedMinutes}:${formattedSeconds}`
}

export const formatDeltaTimeVariantAndIcon = delta => {
  if (delta < 0) {
    return {
      text: `${formatTimeDeltaSeconds (0, 0)}`,
      variant: 'alternative',
      icon: 'tabler-wheelchair',
    }
  }
  const is_error = delta <= 30000
  const is_warning = delta <= 600000
  if (is_error) {
    return {
      text: `${formatTimeDeltaSeconds (0, delta)}`,
      variant: 'error',
      icon: 'tabler-hourglass-off',
    }
  }
  if (is_warning) {
    return {
      text: `${formatTimeDeltaSeconds (0, delta)}`,
      variant: 'warning',
      icon: 'tabler-hourglass-low',
    }
  }

  return {
    text: `${formatTimeDeltaSeconds (0, delta)}`,
    variant: 'success',
    icon: 'tabler-hourglass-high',
  }
}

export const resolveOrderInStatus = type => {
  if (type === "all") {
    return []
  }
  if (type === "active") {
    return [
      "New",
      "Money sent by user",
    ]
  }
  if (type === "success") {
    return [
      "Completed",
    ]
  }
  if (type === "declined") {
    return [
      "Expired",
      "Cancelled",
      "Cancelled by support",
      "Cannot process",
      "Cancelled by trader",
    ]
  }
  if (type === "arbitrage") {
    return [
      "Arbitrage",
    ]
  }
  if (type === "recalculation") {
    return [
      "Recalculation",
    ]
  }

  return null
}

export const resolveOrderOutStatus = type => {
  if (type === "all") {
    return []
  }
  if (type === "active") {
    return [
      "New",
      "Money sent by trader",
    ]
  }
  if (type === "success") {
    return [
      "Completed",
    ]
  }
  if (type === "declined") {
    return [
      "Failed","Cancelled by support","Cancelled","Expired","Cannot process",
    ]
  }
  if (type === "manual") {
    return [
      "Manual check",
    ]
  }
  if (type === "recalculation") {
    return [
      "Recalculation",
    ]
  }

  return null
}
