import base64
import time
import json
import os
import string
import sys
import traceback
from datetime import datetime
from decimal import Decimal
from functools import wraps
from web3.exceptions import TransactionNotFound
from curl_cffi.requests import AsyncSession
import pyuseragents
from typing import Iterator
from web3.auto import w3
import random
from loguru import logger
from twitter import Client
from twitter.errors import BadAccountToken, AccountLocked, AccountSuspended, FailedToFindDuplicatePost, ServerError, HTTPException
import twitter
from .galxe_utils.exceptions import TwitterException
from curl_cffi.requests.errors import RequestsError
import twocaptcha
from twocaptcha import TwoCaptcha
import asyncio
import concurrent.futures
from .config import RETRIES
from .models import TxStatusResponse
from .paths import USER_AGENTS
from .paths import APPROVE_ABI, BALANCE_OF_ABI, DECIMALS_ABI, ERC20_ABI
from .run_config import current_run, ROOT_DIR
from faker import Faker


class JSException(Exception):
    pass


class BadTwitterTokenException(Exception):
    def __init__(self, token):
        self.token = token
        super().__init__()

    def __str__(self):
        return f"Bad token: {self.token}. Replace it to new one"


def get_new_db_path_name():
    db_path = os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'database')
    dbs_names = [f for f in os.listdir(db_path) if f.endswith(".db")]
    while True:
        fake_word = Faker().word()
        new_db_name = f"{current_run.PACKAGE[4:]}-{fake_word}.db"
        if new_db_name in dbs_names:
            continue
        return  os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'database', new_db_name)


def build_db_path(db_name):
    return os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'database', db_name)


def build_logs_path(log_name):
    return os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'logs', log_name)


def build_statuses_path(status_name):
    return os.path.join(ROOT_DIR, current_run.PACKAGE, 'data', 'statuses', status_name)


class LockedTwitterTokenException(Exception):
    def __init__(self, token):
        self.token = token
        super().__init__()

    def __str__(self):
        return f"Locked twitter with token: {self.token}. You can try to solve captcha to unlock it"


class SuspendedTwitterTokenException(Exception):
    def __init__(self, token):
        self.token = token
        super().__init__()

    def __str__(self):
        return f"Banned twitter with token: {self.token}"


class BadTokenDiscordException(Exception):
    def __init__(self, token):
        self.token = token
        super().__init__()

    def __str__(self):
        return f"Bad discord with token: {self.token}"


def get_projects(module):
    current_directory = os.path.dirname(os.path.abspath(module))
    return [f for f in os.listdir(current_directory) if f.startswith('run_')]


def get_session(url: str, proxy: str = None, user_agent=None) -> AsyncSession:
    user_agent = user_agent if user_agent else random.choice(list(get_data_lines(USER_AGENTS)))
    headers = {
        'Accept': '*/*',
        'Accept-Language': 'uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6',
        'Connection': 'keep-alive',
        'Origin': url,
        'Referer': url,
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-site',
        'User-Agent': user_agent,
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
    }
    session = AsyncSession(
        headers=headers,
        impersonate="chrome110",
        verify=False,
        trust_env=True
    )
    if proxy:
        session.proxies = proxy
    return session


def get_data_lines(path) -> Iterator[str]:
    with open(path) as file:
        for line in file:
            yield line.strip()


def get_utc_now():
    current_time_utc = datetime.utcnow()
    utc_now = current_time_utc.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    return utc_now


def get_created_wallet():
    account = w3.eth.account.create()
    return {
        'address': account.address,
        'pk': account._private_key.hex()
    }


def generate_random(length):
    letters_and_digits = string.ascii_letters + string.digits
    value = ''.join(random.choice(letters_and_digits) for _ in range(length))
    return value


def generate_random_hex_string(length):
    hex_characters = string.hexdigits.lower()
    random_hex_string = ''.join(random.choice(hex_characters) for _ in range(length))
    return random_hex_string


def generate_url_safe_base64(length):
    random_bytes = os.urandom(32)
    base64_urlsafe_str = base64.urlsafe_b64encode(random_bytes).decode('utf-8')
    base64_urlsafe_str = base64_urlsafe_str.rstrip('=')
    if len(base64_urlsafe_str) < length:
        base64_urlsafe_str += 'A' * (length - len(base64_urlsafe_str))
    elif len(base64_urlsafe_str) > length:
        base64_urlsafe_str = base64_urlsafe_str[:length]
    return base64_urlsafe_str


class MaxLenException(Exception):
    message = 'Cloudflare'


class Logger:
    def __init__(self, client_address: str, *, additional: dict | None = None):
        additional = {} if additional is None else additional
        self.pk = additional.get('pk')
        self.proxy = additional.get('proxy')
        self.seed = additional.get('seed')
        self.client_address = client_address
        values_to_bind = {k: v for k, v in {'client_address': self.client_address,
                                            'pk': f'{self.pk[-6:]}' if self.pk else None,
                                            'seed': f'"{" ".join(self.seed.split()[-2:])}"' if self.seed else 'None',
                                            'proxy': self.proxy.split('@')[-1] if self.proxy else 'None'}.items() if v}
        self.logger = logger.bind(**values_to_bind)
        self.logger_settings()

    def logger_settings(self):
        self.logger.remove()
        self.logger.add(sys.stdout, format=self.format_record, colorize=True)
        self.logger.add(build_logs_path(f"{current_run.PACKAGE}-{time.strftime('%Y-%m-%d')}"),
            format=self.format_record,
            level="INFO",
            rotation="500 MB",
            retention="7 days"
        )

    def format_record(self, record):
        if record['extra'].get('func_name'):
            logger_format = (
                "<fg #9ACD32>{time:MMM-DD|HH:mm:ss}</fg #9ACD32> - <fg #9ACD32>{extra[func_module]}.{extra[func_name]}</fg #9ACD32> - "
            )
        else:
            logger_format = (
                "<fg #9ACD32>{time:MMM-DD|HH:mm:ss}</fg #9ACD32> - <fg #9ACD32>{module}.{function}</fg #9ACD32> - "
            )
        if self.pk:
            logger_format += "<cyan>PK:</cyan> <fg #9370DB>{extra[pk]}</fg #9370DB>"
        if self.seed:
            logger_format += "<cyan>SEED:</cyan> <fg #9370DB>{extra[seed]}</fg #9370DB>"
        if self.proxy:
            logger_format += " | <cyan>PROXY:</cyan> <fg #9370DB>{extra[proxy]}</fg #9370DB>"
        logger_format += " | <cyan>Address:</cyan> <fg #8A2BE2>{extra[client_address]}</fg #8A2BE2>"
        logger_format += " - <level>{level}"
        if record["level"].name == "ERROR":
            logger_format += "<red> - {message}</red></level>\n"
        else:
            logger_format += " - {message}</level>\n"
        return logger_format


async def sleep(a=3, b=None):
    if not b:
        await asyncio.sleep(a)
    else:
        sleep_for = random.randint(a, b)
        await asyncio.sleep(sleep_for)


def check_res_status(expected_statuses=(200, 201), success_message=None):
    def outer(func):
        @wraps(func)
        async def wrapper(obj, *args, **kwargs):
            logger = obj.logger.bind(func_name=func.__name__, func_module=func.__module__)
            res = await func(obj, *args, **kwargs)
            status = res.status_code
            if status not in expected_statuses:
                if len(res.text) > 300 and any(i in res.text for i in['Just a moment', 'Cloudflare']):
                    raise MaxLenException('Cloudflare')
                logger.error(f'Error! Actual status={status}. Expected={expected_statuses}')
                logger.error(f'Response: {res.text}')
                raise RequestsError(f"Expected statuses {expected_statuses}, got {status}")
            if success_message:
                logger.success(success_message)
            return res
        return wrapper
    return outer


def retry(retries=RETRIES):
    def decorator_retry(func):
        @wraps(func)
        async def wrapper_retry(obj, *args, **kwargs):
            logger = obj.logger.bind(func_name=func.__name__, func_module=func.__module__)
            attempts = 1
            while True:
                try:
                    return await func(obj, *args, **kwargs)
                except MaxLenException:
                    raise
                except Exception as e:
                    if attempts > retries:
                        raise
                    logger.error(f"{e}. Attempt {attempts}.")
                    attempts += 1
                    await sleep(20, 30)
        return wrapper_retry
    return decorator_retry


class Contract:
    def __init__(self, client) -> None:
        self.client = client

    async def get_contract(self, contract_address, abi):
        return self.client.w3.eth.contract(address=contract_address, abi=abi)


def read_json(file_path):
    with open(file_path, 'r') as file:
        data = file.read()
        return json.loads(data)


def wait_tx_status(max_wait_time=100,
                   success_message='Transaction for checkin DONE',
                   error_message="Can't do checkin",
                   explorer='https://bscscan.com/tx/'):
    def outer(func):
        @wraps(func)
        async def wrapper(obj, *args, **kwargs):
            start_time = time.time()
            while True:
                try:
                    tx_hash = await func(obj, *args, **kwargs)
                    await sleep(7, 10)
                    receipts = await obj.client.w3.eth.get_transaction_receipt(tx_hash)
                    status = receipts.get("status")
                    if status == 1:
                        obj.logger.success(f'{success_message}. HASH - {explorer}{tx_hash}')
                        await asyncio.sleep(3)
                        return tx_hash
                    elif status is None:
                        obj.logger.debug('Something went wrong, one more attempt...')
                        await asyncio.sleep(3)
                    else:
                        obj.logger.error(f"{error_message}. HASH - {explorer}{tx_hash}")
                        return
                except TransactionNotFound:
                    if time.time() - start_time > max_wait_time:
                        obj.logger.error(f"{error_message}. HASH - {explorer}{tx_hash}")
                        return
                    obj.logger.debug('Transaction not found, one more attempt. Sleeping some time...')
                    await asyncio.sleep(5)
                except Exception as e:
                    obj.logger.error(f'Unknown error! {e}')
                    return
        return wrapper
    return outer


class CaptchaSolverMain:
    def __init__(self, two_captcha_api_key: str, logger: logger, proxy: str = None):
        if two_captcha_api_key == "":
            raise Exception("2captcha API key is missing. Set it in settings.py")

        self.config = {
            "apiKey": two_captcha_api_key,
        }

        self.proxy = proxy
        self.logger = logger
        self.solver = TwoCaptcha(**self.config)

    def get_balance(self):
        return self.solver.balance()

    def solve(self):
        pass

async def solve_captcha(self):
    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        while True:
            try:
                solution = await loop.run_in_executor(pool, lambda: self.solve())
                self.logger.success('Captcha solved successfully!')
                return solution['code']
            except twocaptcha.api.ApiException as e:
                self.logger.error(f'Error with solving captcha. {e}. Trying again...')
            except twocaptcha.TimeoutException as e:
                self.logger.error(f'Captcha timed out. Trying again...')
            except Exception as e:
                self.logger.error(f'Captcha exception: {e}\n{traceback.format_exc()}')


def retry_js(func):
    @wraps(func)
    async def wrapper(obj, *args, **kwargs):
        retries = 20
        while retries:
            try:
                return await func(obj, *args, **kwargs)
            except JSException:
                await sleep(10, 300)
                obj.logger.error('JSException occured. Trying again...')
                retries -= 1
                continue
    return wrapper

async def get_gas_params(obj):
    latest_block = await obj.client.w3.eth.get_block("latest")
    base_fee_per_gas = latest_block["baseFeePerGas"]
    max_priority_fee = await obj.client.w3.eth.max_priority_fee
    max_priority_fee = int(max_priority_fee * 1.1)
    max_fee_per_gas = int(max_priority_fee + int(base_fee_per_gas * 1.1))
    return {
        "maxPriorityFeePerGas": max_priority_fee,
        "maxFeePerGas": max_fee_per_gas,
    }

async def estimate_gas(obj, transaction):
    retries = 3
    for i in range(1, retries+1):
        try:
            estimated = await obj.client.w3.eth.estimate_gas(transaction)
            return int(estimated * 1.01)
        except Exception as e:
            obj.logger.error(f"Error estimating gas: {e}. Trying again {i}/{retries}")

def pass_transaction(success_message='Transaction passed'):
    def outer(func):
        async def wrapper(obj, *args, **kwargs):
            attempts = 10
            completed = False
            while attempts:
                try:
                    if not completed:
                        tx_hash = await func(obj, *args, **kwargs)
                        completed = True
                    await sleep(7, 10)
                    receipts = await obj.client.w3.eth.get_transaction_receipt(tx_hash)
                    status = receipts.get("status")
                    if status == 1:
                        obj.logger.success(f'{success_message}')
                        await sleep()
                        return TxStatusResponse.GOOD
                    else:
                        obj.logger.error(f'Status {status}')
                except TimeoutError:
                    raise RequestsError("Timeout error!")
                except Exception as e:
                    if 'proxy authentication required' in str(e).lower():
                        raise RequestsError("Proxy authentication required")
                    obj.logger.error(f'Error! {type(e)}{e}. Trying again...')
                    await sleep(10, 30)
                    attempts -= 1
        return wrapper
    return outer


@pass_transaction(success_message="Asset successfully approved")
async def approve_asset(obj, contract, spender, value=None):
    obj.logger.info('Starting approving...')
    approve_abi = read_json(APPROVE_ABI)
    contract_address = obj.client.w3.to_checksum_address(contract)
    spender = obj.client.w3.to_checksum_address(spender)
    value = (2 ** 256 - 1) if not value else value
    contract = await Contract(obj.client).get_contract(
        contract_address=contract_address,
        abi=approve_abi)
    gas_params = await get_gas_params(obj)
    transaction = await contract.functions.approve(spender, value).build_transaction(
        {
            'chainId': await obj.client.w3.eth.chain_id,
            'from': obj.client.address,
            'nonce': await obj.client.w3.eth.get_transaction_count(obj.client.address),
            **gas_params
        })
    gas = await estimate_gas(obj, transaction)
    transaction['gas'] = gas
    signed_txn = obj.client.w3.eth.account.sign_transaction(transaction, private_key=obj.client.key)
    tx_hash = await obj.client.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    return tx_hash.hex()

async def asset_balance(obj, asset='eth'):
    if asset == 'eth':
        return obj.client.w3.from_wei(await obj.client.w3.eth.get_balance(obj.client.address), 'ether')
    contract = await Contract(obj.client).get_contract(
        contract_address=obj.client.w3.to_checksum_address(asset),
        abi=read_json(BALANCE_OF_ABI))
    return await contract.functions.balanceOf(obj.client.address).call()

async def get_decimals(obj, contract):
    contract = obj.client.w3.to_checksum_address(contract)
    contract = await Contract(obj.client).get_contract(
        contract_address=obj.client.w3.to_checksum_address(contract),
        abi=read_json(DECIMALS_ABI))
    return await contract.functions.decimals().call()

async def approve_if_insufficient_allowance(obj, contract_address, spender, value=2**256-1):
    contract = obj.client.w3.to_checksum_address(spender)
    contract = await Contract(obj.client).get_contract(
        contract_address=obj.client.w3.to_checksum_address(contract),
        abi=read_json(ERC20_ABI))
    current_allowance = await contract.functions.allowance(
        obj.client.address,
        obj.client.w3.to_checksum_address(contract_address)
    ).call()
    if current_allowance < value:
        obj.logger.info(f"Need approve!")
        await approve_asset(obj, spender, contract_address)

async def get_tokens_with_any_balance(obj, tokens: dict[str, dict[str, str | int]]):
    tokens_with_balance = []
    native_balance = await obj.client.w3.eth.get_balance(obj.client.address)
    if native_balance > 0:
        native_amount = float(obj.client.w3.from_wei(native_balance, 'ether'))
        tokens_with_balance.append(("eth", native_amount))

    for token in tokens:
        if token != 'eth':
            token_contract = await Contract(obj.client).get_contract(
                contract_address=obj.client.w3.to_checksum_address(tokens[token]["address"]),
                abi=read_json(ERC20_ABI))
            balance = await token_contract.functions.balanceOf(obj.client.address).call()
            if balance > 0:
                decimals = tokens[token]["decimals"]
                amount = float(Decimal(str(balance)) / Decimal(str(10 ** decimals)))
                tokens_with_balance.append((token, amount))
    return tokens_with_balance