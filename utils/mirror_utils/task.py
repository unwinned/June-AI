from utils.utils import Logger, retry, check_res_status, generate_url_safe_base64
import json
import secrets
import base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
import datetime
import time


class MirrorTask(Logger):
    def __init__(self, session, client):
        self.session = session
        self.client = client
        super().__init__(self.client.address)

    async def login(self):
        await self.sign_in_session()
        self.logger.success('Successfully logged in mirror.xyz')

    @retry()
    @check_res_status()
    async def sign_in_session(self):
        url = 'https://mirror.xyz/api/graphql'
        x_b64, y_b64, key = self.get_key()
        now = datetime.datetime.now()
        iso_time = now.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        nonce = ''.join(
            secrets.choice('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(17)
        )
        message_to_sign = f"mirror.xyz wants you to sign in with your Ethereum account:\n{self.client.address}\n\nSign in with public key: ('crv':'P-256','ext':true,'key_ops':['verify'],'kty':'EC','x':'{x_b64}','y':'{y_b64}')\n\nURI: https://mirror.xyz\nVersion: 1\nChain ID: 1\nNonce: {nonce}\nIssued At: {iso_time}"
        json_data = {
            "operationName": "signIn",
            "variables": {
                "address": self.client.address,
                "publicKey": key,
                "signature": self.client.get_signed_code(message_to_sign),
                "message": message_to_sign
            },
            "query": "mutation signIn($address: String!, $publicKey: String!, $signature: String!, $message: String!) {\n  signIn(\n    address: $address\n    publicKey: $publicKey\n    signature: $signature\n    message: $message\n  ) {\n    _id\n    __typename\n  }\n}\n"
        }
        return await self.session.post(url, json=json_data)

    @staticmethod
    def get_key():
        curve = ec.SECP256R1()
        backend = default_backend()
        public_key = ec.generate_private_key(curve, backend).public_key()
        x = public_key.public_numbers().x
        y = public_key.public_numbers().y
        x_b64 = base64.urlsafe_b64encode(x.to_bytes(32, 'big')).rstrip(b'=').decode()
        y_b64 = base64.urlsafe_b64encode(y.to_bytes(32, 'big')).rstrip(b'=').decode()
        public_key_dict = {
            "crv": "P-256",
            "ext": True,
            "key_ops": ["verify"],
            "kty": "EC",
            "x": x_b64,
            "y": x_b64
        }
        return x_b64, y_b64, json.dumps(public_key_dict)

    @staticmethod
    def split_url(url_link):
        url_parts = url_link.split("/")
        digest = url_parts[4] if len(url_parts) > 4 else url_parts[3]
        return digest
