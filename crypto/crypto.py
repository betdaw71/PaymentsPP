import json
import os
from decimal import Decimal
from tronpy import Tron
from tronpy.contract import Contract
from tronpy.keys import PrivateKey
from tronpy.providers import HTTPProvider
from tronpy.exceptions import AddressNotFound
from database import add_address, get_private_key, get_all_addresses

SENDER_ADDRESS = os.getenv('SENDER_ADDRESS')
SENDER_PRIVATE_KEY = os.getenv('SENDER_PRIVATE_KEY')
BANK_ADDRESS = os.getenv('BANK_ADDRESS')


provider = HTTPProvider(api_key=os.getenv('TRONGRID_KEY'))
client = Tron(provider=provider)

TARGET_BALANCE = Decimal(os.getenv('TRX_TARGET_BALANCE'))


BALANCE_CHECKER_ADDRESS = os.getenv('BALANCE_CHECKER_ADDRESS')
USDT_ADDRESS = os.getenv('USDT_ADDRESS')
FEE_VALUE = Decimal(os.getenv('FEE_VALUE'))


with open('files/ABI/BalanceCheckerABI.json') as f:
    balance_checker_abi = json.load(f)


with open('files/ABI/TRC20ABI.json') as f:
    usdt_abi = json.load(f)


usdt = Contract(client=client, addr=USDT_ADDRESS, abi=usdt_abi)
balance_checker = Contract(client=client, addr=BALANCE_CHECKER_ADDRESS, abi=balance_checker_abi)


def generate_address() -> (str, str):
    private_key = PrivateKey.random()

    public_address = private_key.public_key.to_base58check_address()
    return public_address, private_key.hex()


def get_usdt_balances(addresses) -> dict:
    response = balance_checker.functions.balances(addresses, USDT_ADDRESS)
    result = {}
    for i in range(len(addresses)):
        result[addresses[i]] = Decimal(response[i]) / 10 ** 6
    return result


def get_trx_balances(addresses) -> dict:
    result = {}

    for address in addresses:
        result[address] = client.get_account_balance(address)

    return result


def get_trx_balance(address):
    try:
        balance = client.get_account_balance(address)
    except AddressNotFound as e:
        balance = Decimal(0)
    return balance



def send_trx(amount, to_address):
    private_key_obj = PrivateKey(bytes.fromhex(SENDER_PRIVATE_KEY))
    public_address = private_key_obj.public_key.to_base58check_address()

    txn = (
        client.trx.transfer(SENDER_ADDRESS, to_address, int(amount * 10**6))
        .build()
        .inspect()
        .sign(private_key_obj)
    )

    result = txn.broadcast().wait()

    return result


def withdraw_usdt(from_address, amount):
    private_key_obj = PrivateKey(bytes.fromhex(get_private_key(from_address)))
    amount_in_smallest_unit = int(amount * 10 ** 6)

    txn = usdt.functions.transfer(BANK_ADDRESS, amount_in_smallest_unit).with_owner(from_address).fee_limit(50_000_000).build()

    txn.sign(private_key_obj)

    result = txn.broadcast()

    return result


def create_address():
    public_address, private_key = generate_address()
    add_address(public_address, private_key)
    return public_address


def refill_address(address):
    needed = TARGET_BALANCE - get_trx_balance(address)
    if needed > 0:
        send_trx(needed, address)


def get_deposits():
    deposits = []
    addresses = get_all_addresses()
    usdt_balances = get_usdt_balances(addresses)

    for address in usdt_balances.keys():
        if usdt_balances[address] > FEE_VALUE:
            deposits.append({"address": address, "amount": usdt_balances[address]})

    return deposits


def process_deposits(deposits):
    for deposit in deposits:
        address = deposit['address']
        refill_address(address)
        withdraw_usdt(address, deposit['amount'])
