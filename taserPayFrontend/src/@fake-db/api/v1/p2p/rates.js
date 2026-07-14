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
        "avatar": "/src/assets/images/misc/currencies/crypto/USDT.png",
        "fiat": [
          {
            "id": "0000-0000-0000-0000",
            "name": "USD",
            "avatar": "/src/assets/images/misc/currencies/crypto/USDT.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0001",
            "name": "RUB",
            "avatar": "/src/assets/images/misc/currencies/fiat/RUB.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0002",
            "name": "EUR",
            "avatar": "/src/assets/images/misc/currencies/fiat/EUR.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0003",
            "name": "UAH",
            "avatar": "/src/assets/images/misc/currencies/fiat/UAH.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0004",
            "name": "TRY",
            "avatar": "/src/assets/images/misc/currencies/fiat/TRY.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
        ]
      },
      {
        "id": "0000-0000-0000-0001",
        "name": "BUSD",
        "avatar": "/src/assets/images/misc/currencies/crypto/BUSD.png",
        "fiat": [
          {
            "id": "0000-0000-0000-0000",
            "name": "USD",
            "avatar": "/src/assets/images/misc/currencies/crypto/USDT.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0001",
            "name": "RUB",
            "avatar": "/src/assets/images/misc/currencies/fiat/RUB.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0002",
            "name": "EUR",
            "avatar": "/src/assets/images/misc/currencies/fiat/EUR.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0003",
            "name": "UAH",
            "avatar": "/src/assets/images/misc/currencies/fiat/UAH.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0004",
            "name": "TRY",
            "avatar": "/src/assets/images/misc/currencies/fiat/TRY.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
        ]
      },
      {
        "id": "0000-0000-0000-0002",
        "name": "BNB",
        "avatar": "/src/assets/images/misc/currencies/crypto/BNB.png",
        "fiat": [
          {
            "id": "0000-0000-0000-0000",
            "name": "USD",
            "avatar": "/src/assets/images/misc/currencies/crypto/USDT.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0001",
            "name": "RUB",
            "avatar": "/src/assets/images/misc/currencies/fiat/RUB.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0002",
            "name": "EUR",
            "avatar": "/src/assets/images/misc/currencies/fiat/EUR.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0003",
            "name": "UAH",
            "avatar": "/src/assets/images/misc/currencies/fiat/UAH.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0004",
            "name": "TRY",
            "avatar": "/src/assets/images/misc/currencies/fiat/TRY.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
        ]
      },
      {
        "id": "0000-0000-0000-0003",
        "name": "ETH",
        "avatar": "/src/assets/images/misc/currencies/crypto/ETH.png",
        "fiat": [
          {
            "id": "0000-0000-0000-0000",
            "name": "USD",
            "avatar": "/src/assets/images/misc/currencies/crypto/USDT.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0001",
            "name": "RUB",
            "avatar": "/src/assets/images/misc/currencies/fiat/RUB.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0002",
            "name": "EUR",
            "avatar": "/src/assets/images/misc/currencies/fiat/EUR.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0003",
            "name": "UAH",
            "avatar": "/src/assets/images/misc/currencies/fiat/UAH.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0004",
            "name": "TRY",
            "avatar": "/src/assets/images/misc/currencies/fiat/TRY.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
        ]
      },
      {
        "id": "0000-0000-0000-0004",
        "name": "DAI",
        "avatar": "/src/assets/images/misc/currencies/crypto/DAI.png",
        "fiat": [
          {
            "id": "0000-0000-0000-0000",
            "name": "USD",
            "avatar": "/src/assets/images/misc/currencies/crypto/USDT.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 10,
                  "maker": 10
                },
                "SELL": {
                  "taker": 10,
                  "maker": 10
                },
                "t-t": 0.1,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.1
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 10,
                  "maker": 10
                },
                "SELL": {
                  "taker": 10,
                  "maker": 10
                },
                "t-t": 0.1,
                "t-m": 0.2,
                "m-t": 0.2,
                "m-m": -0.1
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.123,
                "t-m": 0.412,
                "m-t": 0.1412,
                "m-m": -0.124
              },
            ]
          },
          {
            "id": "0000-0000-0000-0001",
            "name": "RUB",
            "avatar": "/src/assets/images/misc/currencies/fiat/RUB.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0002",
            "name": "EUR",
            "avatar": "/src/assets/images/misc/currencies/fiat/EUR.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0003",
            "name": "UAH",
            "avatar": "/src/assets/images/misc/currencies/fiat/UAH.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
          {
            "id": "0000-0000-0000-0004",
            "name": "TRY",
            "avatar": "/src/assets/images/misc/currencies/fiat/TRY.png",
            "banks": [
              {
                "id": "0000-0000-0000-0000",
                "name": "Sberbank",
                "avatar": "/src/assets/images/misc/banks/sberbank.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0001",
                "name": "Tinkoff",
                "avatar": "/src/assets/images/misc/banks/tinkoff.png",
                "BUY": {
                  "taker": 70,
                  "maker": 70
                },
                "SELL": {
                  "taker": 70,
                  "maker": 70
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
              {
                "id": "0000-0000-0000-0002",
                "name": "AlfaBank",
                "avatar": "/src/assets/images/misc/banks/alfabank.png",
                "BUY": {
                  "taker": 69.32,
                  "maker": 65.1
                },
                "SELL": {
                  "taker": 71.2,
                  "maker": 70.1
                },
                "t-t": 0.0010703773080010476,
                "t-m": 0.0,
                "m-t": 0.0,
                "m-m": -0.0010715242432359803,
                "24hLiq": 1090
              },
            ]
          },
        ]
      },
    ]
  }
]
mock.onGet ('/api/v1/p2p/rates').reply (config => {
  const {
    cex = 'binance',
    fiat = '0000-0000-0000-0000',
    crypto = '0000-0000-0000-0000',
    perPage = 10,
    currentPage = 1
  } = config.params ?? {}
  const cexLowered = cex.toLowerCase ();
  // console.log(config.params)
  try {
    const cexFiltered = database.find ((item => (item.slug.toLowerCase ().includes (cexLowered)))).crypto;
    const cryptoFiltered = cexFiltered.find ((item => (item.id === crypto))).fiat;
    const filtered = cryptoFiltered.find ((item => (item.id === fiat))).banks;
    const totalPage = Math.ceil (filtered.length / perPage) ? Math.ceil (filtered.length / perPage) : 1
    const total = filtered.length
    return [ 200, { data: paginateArray (filtered, perPage, currentPage), totalPage, total } ]
  } catch (error) {
    console.log (error)
    return [ 200, { data: paginateArray ([], perPage, currentPage), totalPage: currentPage, total: perPage } ]
  }
})
