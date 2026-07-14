import mock from '@/@fake-db/mock'
import { paginateArray } from '@/@fake-db/utlis'

const database = [
  {
    "id": "0000-0000-0000-0000",
    "slug": "binance",
    "crypto": [
      {
        "id": "0000-0000-0000-0000",
        "name": "USDT",
        "ticker": "USDT",
        "avatar": "/src/assets/images/misc/currencies/crypto/USDT.png"
      },
      {
        "id": "0000-0000-0000-0001",
        "name": "BUSD",
        "ticker": "BUSD",
        "avatar": "/src/assets/images/misc/currencies/crypto/BUSD.png"
      },
      {
        "id": "0000-0000-0000-0002",
        "name": "BNB",
        "ticker": "BNB",
        "avatar": "/src/assets/images/misc/currencies/crypto/BNB.png"
      },
      {
        "id": "0000-0000-0000-0003",
        "name": "ETH",
        "ticker": "ETH",
        "avatar": "/src/assets/images/misc/currencies/crypto/ETH.png"
      },
      {
        "id": "0000-0000-0000-0004",
        "name": "DAI",
        "ticker": "DAI",
        "avatar": "/src/assets/images/misc/currencies/crypto/DAI.png"
      },
    ]
  }
]
mock.onGet ('/api/v1/p2p/crypto').reply (config => {
  const { cex = 'binance', perPage = 10, currentPage = 1 } = config.params ?? {}
  const queryLowered = cex.toLowerCase ()
  const filtered = database.find((item => (item.slug.toLowerCase ().includes (queryLowered)))).crypto
  const totalPage = Math.ceil (filtered.length / perPage) ? Math.ceil (filtered.length / perPage) : 1
  const total = filtered.length
  return [ 200, { data: paginateArray (filtered, perPage, currentPage), totalPage, total } ]
})
