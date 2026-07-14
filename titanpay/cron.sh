#!/bin/sh

while true; do
  sleep 3
  response=$(curl -X POST -H "Authorization: Token $API_BOT_KEY" $API_URL/api/v1/trade/update/)
  current_datetime=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$current_datetime] Response: $response"
done