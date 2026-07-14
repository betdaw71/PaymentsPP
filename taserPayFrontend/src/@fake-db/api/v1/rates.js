import mock from '@/@fake-db/mock'

const database = [
  {
    "id": "0000-0000-0000-0001",
    "rate": 61.1958,
    "bank": "ЦБ РФ USD"
  },
  {
    "id": "0000-0000-0000-0001",
    "rate": 61.1958,
    "bank": "ЦБ РФ USD"
  },
  {
    "id": "0000-0000-0000-0001",
    "rate": 61.1958,
    "bank": "ЦБ РФ USD"
  },
  {
    "id": "0000-0000-0000-0001",
    "rate": 61.1958,
    "bank": "ЦБ РФ USD"
  },
  {
    "id": "0000-0000-0000-0001",
    "rate": 61.1958,
    "bank": "ЦБ РФ USD"
  },
  {
    "id": "0000-0000-0000-0001",
    "rate": 61.1958,
    "bank": "ЦБ РФ USD"
  },
]
mock.onGet ('/api/v1/rates').reply (config => {
  const {} = config.params ?? {}
  return [ 200, { data: database } ]
})
