import { Icon } from '@iconify/vue'

const aliases = {
  collapse: 'lucide:chevron-up',
  complete: 'lucide:check',
  cancel: 'lucide:x',
  close: 'lucide:x',
  delete: 'lucide:x',
  clear: 'lucide:x',
  success: 'lucide:circle-check',
  info: 'lucide:info',
  warning: 'lucide:alert-circle',
  error: 'lucide:x',
  prev: 'lucide:chevron-left',
  next: 'lucide:chevron-right',
  checkboxOn: 'custom-checked-checkbox',
  checkboxOff: 'custom-unchecked-checkbox',
  checkboxIndeterminate: 'custom-indeterminate-checkbox',
  delimiter: 'lucide:circle',
  sort: 'lucide:arrow-up',
  expand: 'lucide:chevron-down',
  menu: 'lucide:menu',
  subgroup: 'lucide:chevron-down',
  dropdown: 'lucide:chevron-down',
  radioOn: 'custom-checked-radio',
  radioOff: 'custom-unchecked-radio',
  edit: 'lucide:pencil',
  ratingEmpty: 'custom-star-empty',
  ratingFull: 'custom-star-fill',
  ratingHalf: 'custom-star-half',
  loading: 'lucide:refresh-cw',
  first: 'lucide:chevrons-left',
  last: 'lucide:chevrons-right',
  unfold: 'lucide:arrow-up-down',
  file: 'lucide:paperclip',
  plus: 'lucide:plus',
  minus: 'lucide:minus',
  sortAsc: 'lucide:arrow-up',
  sortDesc: 'lucide:arrow-down',
}

export const iconify = {
  component: props => h(Icon, props),
}
export const icons = {
  defaultSet: 'iconify',
  aliases,
  sets: {
    iconify,
  },
}
