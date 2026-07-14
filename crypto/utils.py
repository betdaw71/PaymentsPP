import json
from decimal import Decimal
from tronpy import Tron
from tronpy.contract import Contract
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider


def generate_address():
    private_key = PrivateKey.random()

    public_address = private_key.public_key.to_base58check_address()
    return public_address, private_key


provider = HTTPProvider(api_key='9ca3dc93-d10e-48f5-9c70-792ca3fb7ee1')
client = Tron(provider=provider)

# Replace these with your actual addresses and chain ID
OPERATOR_ADDRESS = 'YourOperatorContractAddress'
BALANCE_CHECKER_ADDRESS = 'THTpm6P6cPgLEMVaAsXQiRSRB9FcTyUwGx'
USDT_ADDRESS = 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'

with open('files/ABI/BalanceCheckerABI.json') as f:
    balance_checker_abi = json.load(f)

with open('files/ABI/OperatorABI.json') as f:
    operator_abi = json.load(f)

with open('files/ABI/TRC20ABI.json') as f:
    usdt_abi = json.load(f)

operator = Contract(client=client, addr=OPERATOR_ADDRESS, abi=operator_abi)
usdt = Contract(client=client, addr=USDT_ADDRESS, abi=usdt_abi)
balance_checker = Contract(client=client, addr=BALANCE_CHECKER_ADDRESS, abi=balance_checker_abi)


def get_balances(addresses) -> dict:
    response = balance_checker.functions.balances(addresses, USDT_ADDRESS)
    result = {}
    for i in range(len(addresses)):
        result[addresses[i]] = Decimal(response[i]) / 10 ** 6
    return result


def transfer_usdt(to_address, amount, private_key):
    # Convert the amount to the smallest unit (assuming 18 decimals)
    amount_in_smallest_unit = int(amount * 10 ** 6)

    # Build the transaction
    txn = usdt.functions.transfer(to_address, amount_in_smallest_unit).with_owner(private_key).fee_limit(
        1_000_000).build()

    # Sign the transaction
    signed_txn = client.trx.sign(txn, private_key)

    # Broadcast the transaction
    result = client.trx.broadcast(signed_txn)

    print(f"Transaction result: {result}")
    return result


def send_trx(sender_address, amount, to_address, private_key):
    private_key_obj = PrivateKey(bytes.fromhex(private_key))
    public_address = private_key_obj.public_key.to_base58check_address()
    print(public_address)

    txn = (
        client.trx.transfer(sender_address, to_address, amount * 10**6)
        .build()
        .inspect()
        .sign(private_key_obj)
    )

    result = txn.broadcast()
    print(result)

    print(f"Transaction result: {result}")
    return result
