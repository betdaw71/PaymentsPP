/**
 * Flatpickr range "start to end" → django-filter DateTimeFromToRangeFilter.
 * Date-only end becomes 23:59:59. Values that already include time keep it
 * (do not append T23:59:59, which produces invalid "2026-10-01 12:00T23:59:59").
 */
export function toDjangoDateTimeRange (dateRange) {
  if (!dateRange || typeof dateRange !== 'string' || !dateRange.includes(' to '))
    return null

  const parts = dateRange.split(' to ').map(part => part.trim()).filter(Boolean)
  if (parts.length < 2)
    return null

  const toIso = (raw, { endOfDayIfDateOnly }) => {
    const compact = raw.replace(' ', 'T')
    if (/^\d{4}-\d{2}-\d{2}$/.test(raw))
      return endOfDayIfDateOnly ? `${raw}T23:59:59` : `${raw}T00:00:00`
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(compact))
      return `${compact}:00`
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(compact))
      return compact.slice(0, 19)

    return compact
  }

  return `${toIso(parts[0], { endOfDayIfDateOnly: false })},${toIso(parts[1], { endOfDayIfDateOnly: true })}`
}
