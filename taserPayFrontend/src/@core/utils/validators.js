import { isEmpty, isEmptyArray, isNullOrUndefined } from './index'

import i18n from "@/plugins/i18n"

const { t } = i18n.global

// 👉 Required Validator
export const requiredValidator = value => {
  if (isNullOrUndefined (value) || isEmptyArray (value) || value === false)
    return t ('validation.required')

  return !!String (value).trim ().length || t ('validation.required')
}

// 👉 Email Validator
export const emailValidator = value => {
  if (isEmpty (value))
    return true
  const re = /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/
  if (Array.isArray (value))
    return value.every (val => re.test (String (val))) || t ('validation.email')

  return re.test (String (value)) || t ('validation.email')
}

// 👉 Password Validator
export const passwordValidator = password => {
  const regExp = /(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?=.*[!@#$%&*()]).{8,}/
  const validPassword = regExp.test (password)

  return validPassword || t ('validation.password')
}

// 👉 Confirm Password Validator
export const confirmedValidator = (value, target) => value === target || t ('validation.confirmed')

// 👉 Between Validator
export const betweenValidator = (value, min, max) => {
  const valueAsNumber = Number (value)

  return (Number (min) <= valueAsNumber && Number (max) >= valueAsNumber) || t ('validation.between', { min, max })
}

// 👉 Integer Validator
export const integerValidator = value => {
  if (isEmpty (value))
    return true
  if (Array.isArray (value))
    return value.every (val => /^-?[0-9]+$/.test (String (val))) || t ('validation.integer')

  return /^-?[0-9]+$/.test (String (value)) || t ('validation.integer')
}

// 👉 Regex Validator
export const regexValidator = (value, regex, pattern = "") => {
  if (isEmpty (value))
    return true
  let regeX = regex
  if (typeof regeX === 'string')
    regeX = new RegExp (regeX)
  if (Array.isArray (value))
    return value.every (val => regexValidator (val, regeX))

  return regeX.test (String (value)) || t ('validation.regex.default') + (pattern ? ` (${t ('validation.regex.pattern')}: ${pattern})` : '')
}

// 👉 Alpha Validator
export const alphaValidator = value => {
  if (isEmpty (value))
    return true

  return /^[A-Z]*$/i.test (String (value)) || t ('validation.alpha')
}

// 👉 URL Validator
export const urlValidator = value => {
  if (isEmpty (value))
    return true
  const re = /^(http[s]?:\/\/){0,1}(www\.){0,1}[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,5}[\.]{0,1}/

  return re.test (String (value)) || t ('validation.url')
}

// 👉 Length Validator
export const lengthValidator = (value, length) => {
  if (isEmpty (value))
    return true

  return String (value).length === length || t ('validation.length', { length })
}

// 👉 Alpha-dash Validator
export const alphaDashValidator = value => {
  if (isEmpty (value))
    return true
  const valueAsString = String (value)

  return /^[0-9A-Z_-]*$/i.test (valueAsString) || t ('validation.alpha_dash')
}

export const uniqueValidator = (list, index, key, name) => {
  if (isEmpty (list))
    return true
  const value = list[index][key]
  const filteredList = list.filter ((item, i) => i !== index)

  return !filteredList.some (item => item[key] === value) || t ('validation.unique', { name })
}
export const differentValidator = (value1, value2, value1_name, value2_name) => {
  if (isEmpty (value1) || isEmpty (value2))
    return true

  return value1 !== value2 || t ('validation.different', { field: value1_name, other: value2_name })

}
