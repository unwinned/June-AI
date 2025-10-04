from utils.client import Client
from .config import CONFIG
from utils.models import RpcProviders, ChainExplorers
from utils.utils import Logger, sleep
from .utils import pass_transaction
import random


class SelfSender(Logger):
    def __init__(self, clients):
        self.clients = clients
        self.explorer = ChainExplorers.MONAD.value
        self.client = Client(key=CONFIG.SELF_SENDER.SEND_FROM_PK,
                             http_provider=RpcProviders.SAHARA_TESTNET.value)
        super().__init__(self.client.address, additional={'pk': self.client.key})

    @property
    async def balance(self):
        return self.client.w3.from_wei(await self.client.w3.eth.get_balance(self.client.address), 'ether')

    async def run(self):
        self.client.define_new_provider(RpcProviders.SAHARA_TESTNET.value)
        for client in self.clients:
            balance = await self.balance
            random_value_to_send = round(random.uniform(*CONFIG.SELF_SENDER.SEND_AMOUNT), 4)
            if random_value_to_send > balance:
                self.logger.error(f"Not enought SAHARA to send. "
                                  f"Need: {random_value_to_send}, have: {balance}")
                return
            self.logger.info(f"Sending {random_value_to_send} SAHARA to {client.address}...")
            await self.send_transaction(random_value_to_send, client.address)
            await sleep(*CONFIG.SETTINGS.SLEEP_BETWEEN_TASKS)

    @pass_transaction(success_message="SAHARA successfully sent!")
    async def send_transaction(self, value, recipient):
        transaction = {
            'from': self.client.address,
            'to': self.client.w3.to_checksum_address(recipient),
            'value': self.client.w3.to_wei(value, 'ether'),
            'gasPrice': int(await self.client.w3.eth.gas_price * 1.1),
            'nonce': await self.client.w3.eth.get_transaction_count(self.client.address),
            'chainId': await self.client.w3.eth.chain_id
        }
        transaction['gas'] = await self.client.w3.eth.estimate_gas(transaction)
        signed_txn = self.client.w3.eth.account.sign_transaction(transaction, private_key=self.client.key)
        tx_hash = await self.client.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        return tx_hash.hex()