import mock from '@/@fake-db/mock'
import { paginateArray } from '@/@fake-db/utlis'

const database = [
  {
    "id": "0000-0000-0000-0000",
    "slug": "binance",
    "fiat": [
      {
        "id": "0000-0000-0000-0000",
        "name": "USD",
        "symbol": "USD",
        "avatar": "/src/assets/images/misc/currencies/fiat/USD.png"
      },
      {
        "id": "0000-0000-0000-0001",
        "name": "RUB",
        "symbol": "RUB",
        "avatar": "/src/assets/images/misc/currencies/fiat/RUB.png"
      },
      {
        "id": "0000-0000-0000-0002",
        "name": "EUR",
        "symbol": "EUR",
        "avatar": "/src/assets/images/misc/currencies/fiat/EUR.png"
      },
      {
        "id": "0000-0000-0000-0003",
        "name": "UAH",
        "symbol": "UAH",
        "avatar": "/src/assets/images/misc/currencies/fiat/UAH.png"
      },
      {
        "id": "0000-0000-0000-0004",
        "name": "TRY",
        "symbol": "TRY",
        "avatar": "/src/assets/images/misc/currencies/fiat/TRY.png"
      },
    ]
  }
]
mock.onGet ('/api/v1/p2p/fiat').reply (config => {
  const { cex = 'binance', perPage = 10, currentPage = 1 } = config.params ?? {}
  const queryLowered = cex.toLowerCase ()
  const filtered = database.find((item => (item.slug.toLowerCase ().includes (queryLowered)))).fiat
  const totalPage = Math.ceil (filtered.length / perPage) ? Math.ceil (filtered.length / perPage) : 1
  const total = filtered.length
  return [ 200, { data: paginateArray (filtered, perPage, currentPage), totalPage, total } ]
})

