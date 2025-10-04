import concurrent.futures

import twocaptcha
from twocaptcha import TwoCaptcha
import json
from capmonstercloudclient import CapMonsterClient, ClientOptions
from capmonstercloudclient.exceptions import GetBalanceError
from capmonstercloudclient.requests import (GeetestRequest,
                                            RecaptchaV2Request,
                                            RecaptchaV3ProxylessRequest,
                                            TurnstileRequest,
                                            TurnstileProxylessRequest,
                                            HcaptchaRequest,
                                            ImageToTextRequest,)
from urllib.parse import urlparse
import asyncio
import aiohttp
from http.client import HTTPException
from typing import Dict, Union
from utils.utils import retry, check_res_status, get_session, sleep
import base64


class CaptchaSolver:
    def __init__(self, proxy: str = None, api_key: str = None, logger=None):
        if api_key is None:
            raise Exception("2captcha API key is missing. Set it in settings.py")

        self.config = {
            "apiKey": api_key,
        }

        self.proxy = proxy
        self.solver = TwoCaptcha(**self.config)
        self.logger = logger

    def get_balance(self):
        return self.solver.balance()

    def sync_send_bad_report_request(self, captcha_id):
        return self.solver.report(captcha_id, False)

    async def send_report(self, captcha_id):
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, lambda: self.sync_send_bad_report_request(captcha_id))

    def solve(self):
        captcha = self.solver.geetest_v4(captcha_id='244bcb8b9846215df5af4c624a750db4',
                                         url='https://app.galxe.com',
                                         proxy={"type": "HTTP", "uri": self.proxy})
        return captcha

    async def solve_captcha(self, logger):
        self.logger = logger
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            while True:
                try:
                    solution = await loop.run_in_executor(pool, lambda: self.solve())
                    captcha_id = solution['captchaId']
                    logger.success('Captcha solved successfully!')
                    solution_code = json.loads(solution['code'])
                    solution = {
                        'lot_number': solution_code['lot_number'],
                        'seccode': {
                            'captcha_output': solution_code['captcha_output'],
                            'pass_token': solution_code['pass_token'],
                            'gen_time': solution_code['gen_time'],
                        }
                    }
                    return captcha_id, solution
                except twocaptcha.api.ApiException as e:
                    logger.error(f'Error with solving captcha {e}. Trying again...')
                except twocaptcha.api.NetworkException as e:
                    logger.error(f'Network error with solving captcha {e}. Trying again...')
                except twocaptcha.solver.TimeoutException as e:
                    logger.error(f'Timeout exception {e}. Trying again...')

    def solve_img_to_text_request(self, img):
        captcha = self.solver.normal(img,
                                     minLen=6,
                                     maxLem=6,
                                     regsense=1,
                                     language=2,
                                     caseSensitive=True,
                                     proxy={"type": "HTTP", "uri": self.proxy})
        return captcha

    async def solve_img_to_text(self, img):
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            while True:
                try:
                    solution = await loop.run_in_executor(pool, lambda: self.solve_img_to_text_request(img))
                    return solution['captchaId'], solution['code']
                except twocaptcha.api.ApiException as e:
                    self.logger.error(f'Error with solving captcha {e}. Trying again...')
                except twocaptcha.api.NetworkException as e:
                    self.logger.error(f'Network error with solving captcha {e}. Trying again...')
                except twocaptcha.solver.TimeoutException as e:
                    self.logger.error(f'Timeout exception {e}. Trying again...')

    async def send_bad_report(self, captcha_id):
        self.logger.info('Sending bad captcha report...')
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            await loop.run_in_executor(pool, lambda: self.sync_send_bad_report(captcha_id))


class CapmonsterSolver:
    def __init__(self, proxy: str = None, api_key: str = None, logger=None):
        if api_key is None:
            raise Exception("Capmonster API key is missing. Set it in config.py")
        self.config = {
            "api_key": api_key,
            'ssl': False
        }
        self.proxy = proxy
        parsed_url = urlparse(self.proxy)
        self.proxy_type = parsed_url.scheme
        self.proxy_login = parsed_url.username
        self.proxy_password = parsed_url.password
        self.proxy_ip = parsed_url.hostname
        self.proxy_port = parsed_url.port
        self.client_options = ClientOptions(**self.config)
        self.cap_monster_client = CustomCapmonsterClient(options=self.client_options)
        self.logger = logger

    async def solve_geetest4_request(self):
        geetest_4_request = GeetestRequest(gt='244bcb8b9846215df5af4c624a750db4',
                                           websiteUrl='https://app.galxe.com',
                                           version=4,
                                           proxyType=self.proxy_type,
                                           proxyAddress=self.proxy_ip,
                                           proxyPort=self.proxy_port,
                                           proxyLogin=self.proxy_login,
                                           proxyPassword=self.proxy_password,)
        return await self.cap_monster_client.solve_captcha(geetest_4_request)

    async def solve_recaptchav2_request(self, key, url):
        recaptchav2_request = RecaptchaV2Request(websiteUrl=url,
                                                 websiteKey=key,
                                                 proxyType=self.proxy_type,
                                                 proxyAddress=self.proxy_ip,
                                                 proxyPort=self.proxy_port,
                                                 proxyLogin=self.proxy_login,
                                                 proxyPassword=self.proxy_password)
        return await self.cap_monster_client.solve_captcha(recaptchav2_request)

    async def solve_recaptchav3_request(self, key, url, action, min_score):
        recaptchav3_request = RecaptchaV3ProxylessRequest(websiteUrl=url,
                                                          websiteKey=key,
                                                          pageAction=action,
                                                          min_score=min_score)
        return await self.cap_monster_client.solve_captcha(recaptchav3_request)

    async def solve_captcha(self, logger):
        self.logger = logger
        while True:
            try:
                solution = await self.solve_geetest4_request()
                captcha_id = solution['captcha_id']
                logger.success('Captcha solved successfully!')
                solution = {
                    'lot_number': solution['lot_number'],
                    'seccode': {
                        'captcha_output': solution['captcha_output'],
                        'pass_token': solution['pass_token'],
                        'gen_time': solution['gen_time']
                    }
                }
                return captcha_id, solution
            except GetBalanceError:
                logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                logger.error(f'Captcha exception {e}')

    async def solve_recaptchav2(self,
                                url='https://faucet.movementlabs.xyz',
                                key='6LdVjR0qAAAAAFSjzYqyRFsnUDn-iRrzQmv0nnp3'):
        while True:
            try:
                solution = await self.solve_recaptchav2_request(key, url)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def solve_recaptchav3(self,
                                url='https://faucet.movementlabs.xyz',
                                key='6LdVjR0qAAAAAFSjzYqyRFsnUDn-iRrzQmv0nnp3',
                                action='drip_request',
                                min_score=0.9):
        while True:
            try:
                solution = await self.solve_recaptchav3_request(key, url, action, min_score)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def turnstile_cookies_request(self, url, key, cloudflare_response_base64, user_agent):
        turnstile_request = TurnstileRequest(websiteURL=url,
                                             websiteKey=key,
                                             cloudflareTaskType="cf_clearance",
                                             htmlPageBase64=cloudflare_response_base64,
                                             userAgent=user_agent,
                                             proxyType=self.proxy_type,
                                             proxyAddress=self.proxy_ip,
                                             proxyPort=self.proxy_port,
                                             proxyLogin=self.proxy_login,
                                             proxyPassword=self.proxy_password)
        return await self.cap_monster_client.solve_captcha(turnstile_request)

    async def solve_turnstile_cookies(self, url, key, cloudflare_response_base64, user_agent):
        while True:
            try:
                solution = await self.turnstile_cookies_request(url, key, cloudflare_response_base64, user_agent)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def turnstile_request(self, url, key):
        turnstile_request = TurnstileProxylessRequest(websiteURL=url,
                                                      websiteKey=key)
        return await self.cap_monster_client.solve_captcha(turnstile_request)

    async def solve_turnstile(self, url, key):
        while True:
            try:
                solution = await self.turnstile_request(url, key)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def turnstile_token_request(self, url, key):
        turnstile_request = TurnstileRequest(websiteURL=url,
                                             websiteKey=key,
                                             cloudflareTaskType='token',
                                             pageAction='managed',
                                             userAgent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                                             data=None,
                                             pageData=None,
                                             proxyType=self.proxy_type,
                                             proxyAddress=self.proxy_ip,
                                             proxyPort=self.proxy_port,
                                             proxyLogin=self.proxy_login,
                                             proxyPassword=self.proxy_password)
        return await self.cap_monster_client.solve_captcha(turnstile_request)

    async def solve_turnstile_token(self, url, key):
        while True:
            try:
                solution = await self.turnstile_token_request(url, key)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def hcaptcha_request(self, url, key):
        hcaptcha_request = HcaptchaRequest(websiteUrl=url,
                                            websiteKey=key,
                                            proxyType=self.proxy_type,
                                            proxyAddress=self.proxy_ip,
                                            proxyPort=self.proxy_port,
                                            proxyLogin=self.proxy_login,
                                            proxyPassword=self.proxy_password)
        return await self.cap_monster_client.solve_captcha(hcaptcha_request)

    async def solve_hcaptcha(self, url, key):
        while True:
            try:
                solution = await self.hcaptcha_request(url, key)
                return solution
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

    async def img_to_text_request(self, img_base64: str):
        image_to_text_request = ImageToTextRequest(
            image_bytes=base64.b64decode(img_base64),
            recognizingThreshold=85,
            module_name='universal'
        )
        return await self.cap_monster_client.solve_captcha(image_to_text_request)

    async def solve_img_to_text(self, img_base64: str):
        while True:
            try:
                solution = await self.img_to_text_request(img_base64)
                if not isinstance(solution, dict) or "text" not in solution:
                    self.logger.error(f"Unexpected response: {solution}")
                    continue
                captcha_text = solution["text"].upper()
                return captcha_text
            except GetBalanceError:
                self.logger.error('Not enough money to solve the captcha!')
                raise
            except Exception as e:
                self.logger.error(f'Captcha exception {e}')

class BestcaptchaSolver:
    def __init__(self, session, api_key: str = None, logger=None):
        if api_key is None:
            raise Exception("BestcaptchaSolver API key is missing. Set it in config.py")
        self.api_key = api_key
        self.logger = logger
        self.session = session

    async def solve_hcaptcha(self, url, key):
        captcha_response = (await self.solve_hcaptcha_submit(url, key)).json()
        captcha_id = captcha_response['id']
        while True:
            retrive_captcha_response = (await self.solve_hcaptcha_retrieve(captcha_id)).json()
            if retrive_captcha_response['status'] == 'completed':
                self.logger.success("Hcaptcha solved successfully!")
                return retrive_captcha_response['solution']
            elif retrive_captcha_response['status'] == 'pending':
                self.logger.info("Hcaptcha still solving...")
                await sleep(30)
            else:
                self.logger.error(f"Captcha solving error! {retrive_captcha_response}")
                break

    @retry()
    @check_res_status()
    async def solve_hcaptcha_submit(self, page_url, key):
        url = 'https://bcsapi.xyz/api/captcha/hcaptcha'
        json_data= {
            "page_url": page_url,
            "site_key": key,
            "access_token": self.api_key,
            "user_agent": self.session.headers['User-Agent']
        }
        return await self.session.post(url, json=json_data)

    @retry()
    @check_res_status()
    async def solve_hcaptcha_retrieve(self, captcha_id):
        url = f'https://bcsapi.xyz/api/captcha/{captcha_id}?access_token={self.api_key}'
        return await self.session.get(url)

class CustomCapmonsterClient(CapMonsterClient):
    async def _getTaskResult(self, task_id: str) -> Dict[str, Union[int, str, None]]:
        body = {
            'clientKey': self.options.api_key,
            'taskId': task_id
        }
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
            async with session.post(url=self.options.service_url + '/getTaskResult',
                                    json=body,
                                    timeout=aiohttp.ClientTimeout(total=self.options.client_timeout),
                                    headers=self.headers,
                                    ssl=None) as resp:
                if resp.status != 200:
                    if resp.status == 500:
                        return {'errorId': 0, 'status': 'processing'}
                    else:
                        raise HTTPException(f'Cannot grab result. Status code: {resp.status}.')
                else:
                    return await resp.json(content_type=None)

    async def _createTask(self, request) -> Dict[str, Union[str, int]]:
        task = request.getTaskDict()
        body = {
                "clientKey": self.options.api_key,
                "task": task,
                "softId": self.options.default_soft_id
               }
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(verify_ssl=False)) as session:
            async with session.post(url=self.options.service_url + '/createTask',
                                    json=body,
                                    timeout=aiohttp.ClientTimeout(total=self.options.client_timeout),
                                    headers=self.headers,
                                    ssl=None) as resp:
                if resp.status != 200:
                    raise HTTPException(f'Cannot create task. Status code: {resp.status}.')
                else:
                    return await resp.json(content_type=None)