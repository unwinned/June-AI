import asyncio
import hashlib
import random
from contextlib import suppress
from datetime import datetime, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import openai
from playwright.async_api import async_playwright, TimeoutError

from utils.client import Client
from utils.galxe_utils.captcha import CapmonsterSolver
from utils.utils import Logger

from .browser_utils import get_random_user_agent, get_random_timezone
from .config import CONFIG
from .mail_setup import MailSetup
from .paths import referal_codes


class Task(Logger):
    # ---------------------------
    # Lifecycle / init
    # ---------------------------
    def __init__(self, session, client: Client, db_manager):
        self.session = session
        self.client = client
        self.db_manager = db_manager

        self.playwright = None
        self.browser = None
        self.context = None

        self.pages = {}
        self.current_page = None

        self.random_response_time = random.randint(20, 30)
        self._seen_hashes = set()

        super().__init__(
            self.client.address,
            additional={
                'pk': self.client.key,
                'proxy': self.session.proxies.get('http')
            }
        )

        # (оставил — логика не тронута, просто инициализация)
        self.captcha_solver = CapmonsterSolver(
            proxy=self.session.proxies.get('http'),
            api_key=CONFIG.SOLVERS.CAPSOLVER_API_KEY,
        )

    async def start_for_login(self):
        self.playwright = await async_playwright().start()

        proxy_url = self.session.proxies.get('http')
        proxy = urlparse(proxy_url) if proxy_url else None

        prep_proxy = None
        if proxy:
            prep_proxy = {"server": f"http://{proxy.hostname}:{proxy.port}"}
            if proxy.username and proxy.password:
                prep_proxy["username"] = proxy.username
                prep_proxy["password"] = proxy.password

        user_agent, chrome_version = get_random_user_agent()
        user_data_dir = f'./browsers_data/{self.client.address}_browser_data'

        self.browser = await self.playwright.chromium.launch_persistent_context(
            headless=False,
            user_data_dir=str(user_data_dir),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process,OptimizationGuideModelDownloading,OptimizationHintsFetching,OptimizationTargetPrediction,OptimizationHints",
                "--disable-site-isolation-trials",
                "--disable-setuid-sandbox",
                "--ignore-certificate-errors",
                "--disable-logging",
            ],
            user_agent=user_agent,
            proxy=prep_proxy,
            java_script_enabled=True,
            locale="en-US",
            timezone_id=get_random_timezone(),
        )

        await self.browser.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
        """)

        for page in self.browser.pages:
            await page.set_extra_http_headers({
                "accept": "*/*",
                "accept-language": "en-US,en;q=0.9",
                "sec-ch-ua": f'"Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "cross-site",
            })

    async def start(self):
        self.playwright = await async_playwright().start()

        proxy_url = self.session.proxies.get('http')
        proxy = urlparse(proxy_url) if proxy_url else None

        prep_proxy = None
        if proxy:
            prep_proxy = {"server": f"http://{proxy.hostname}:{proxy.port}"}
            if proxy.username and proxy.password:
                prep_proxy["username"] = proxy.username
                prep_proxy["password"] = proxy.password

        user_agent, chrome_version = get_random_user_agent()
        user_data_dir = f'./browsers_data/{self.client.address}_browser_data'

        self.browser = await self.playwright.chromium.launch_persistent_context(
            headless=True,
            user_data_dir=str(user_data_dir),
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process,OptimizationGuideModelDownloading,OptimizationHintsFetching,OptimizationTargetPrediction,OptimizationHints",
                "--disable-site-isolation-trials",
                "--disable-setuid-sandbox",
                "--ignore-certificate-errors",
                "--disable-logging",
            ],
            user_agent=user_agent,
            proxy=prep_proxy,
            java_script_enabled=True,
            locale="en-US",
            timezone_id=get_random_timezone(),
        )

        await self.browser.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
        """)

        for page in self.browser.pages:
            await page.set_extra_http_headers({
                "accept": "*/*",
                "accept-language": "en-US,en;q=0.9",
                "sec-ch-ua": f'"Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "cross-site",
            })

    async def stop(self):
        if self.browser:
            with suppress(Exception):
                for p in list(self.browser.pages):
                    with suppress(Exception):
                        await p.close()
            with suppress(Exception):
                await self.browser.close()
            self.browser = None
        if self.playwright:
            with suppress(Exception):
                await self.playwright.stop()
            self.playwright = None

    async def new_page(self, name: str):
        page = await self.browser.new_page()
        self.pages[name] = page
        self.current_page = page
        return page

    def switch_page(self, name: str):
        if name in self.pages:
            self.current_page = self.pages[name]
        else:
            raise ValueError("Page not found")

    # ---------------------------
    # UI helpers
    # ---------------------------
    async def dismiss_overlays(self):
        candidates = [
            ".reactour__close-button",
            "//div[@role='dialog']//button[.//text()[normalize-space()='Close'] or @aria-label='Close']",
            "//body/div[4]/button",
            "//body/div[3]/button",
            "//*[@id='CybotCookiebotDialogBodyButtonDecline']",
            "//div[@data-state='open']//button[.='Got it' or .='OK' or .='Close']",
        ]

        with suppress(Exception):
            await self.current_page.keyboard.press("Escape")
            await self.current_page.keyboard.press("Escape")

        for sel in candidates:
            with suppress(Exception):
                await self.current_page.locator(sel).first.click(timeout=1200)

        with suppress(TimeoutError):
            await self.current_page.locator(
                "[role='dialog'], .reactour__helper, #CybotCookiebotDialog"
            ).first.wait_for(state="hidden", timeout=1500)

    # ---------------------------
    # Auth / onboarding
    # ---------------------------
    async def login_june(self):
        await self.start_for_login()
        await self.new_page("june_login")
        await self.current_page.goto("https://askjune.ai/app/chat")

        login_in_btn = self.current_page.locator(
            '//div[1]/div[2]/div/div[2]/div/div[3]/div[2]/div[1]/button'
        )
        await login_in_btn.click()

        input_email = self.current_page.locator('//*[@id="email"]')
        await input_email.type(self.client.email)

        confirm_email_btn = self.current_page.locator('//div/div/div/form/div[2]/button')
        await confirm_email_btn.click()

        await asyncio.sleep(6)

        code = await self.setup_mails()

        code_paste = self.current_page.locator(
            '//div[1]/div/div/form/div[1]/div/div[1]/div/input'
        )
        await code_paste.type(code)

        checkbox_fld = self.current_page.locator(
            '//div[1]/div/div/form/div[2]/label/div[1]/div'
        )
        await checkbox_fld.click()

        confirm_code = self.current_page.locator('//div[1]/div/div/form/div[3]/div/button')
        await confirm_code.click()

        await asyncio.sleep(7)

        with suppress(Exception):
            await self.current_page.locator(
                '//div[1]/div/div[4]/div[1]/div/div[2]/button[4]', timeout=2000
            ).click()

        await self.current_page.keyboard.press("Escape")

        with suppress(Exception):
            await self.current_page.locator('//body/div[4]/button', timeout=2000).click()

        with suppress(Exception):
            await self.current_page.locator('//*[@id=":rb:"]', timeout=2000).type(
                await self.choose_referal_code()
            )

        with suppress(Exception):
            await self.current_page.locator(
                '//*[@id="radix-:r8:"]/div[2]/form/div[2]/button', timeout=2000
            ).click()

        await self.dismiss_overlays()

        await asyncio.sleep(6)

        await self.stop()

    async def choose_referal_code(self):
        with open(referal_codes, 'r', encoding="utf-8") as file:
            codes = file.read().splitlines()

        if not codes:
            return None

        ref_code = random.choice(codes)

        codes.remove(ref_code)
        with open(referal_codes, 'w', encoding="utf-8") as file:
            file.write("\n".join(codes))

        return ref_code

    # ---------------------------
    # App actions
    # ---------------------------
    async def read_points(self):
        await self.start()
        await self.new_page("june")
        await self.current_page.goto("https://askjune.ai/app/chat")
        self.logger.info("Reading points, stay tuned...")

        points_elem = self.current_page.locator(
            '//div[2]/div/div[3]/div[2]/div/button/div/div[1]/div/span[2]/span[1]'
        )
        points = await points_elem.inner_text()
        self.logger.info(f"You've earned {points} points so far!")

        await self.stop()

    async def delete_chats(self):
        random_sleep_time = random.randint(3, 6)

        await self.start()
        await self.new_page("june")
        await self.current_page.goto("https://askjune.ai/app/chat")
        self.logger.info("Deleting chats...")
        await asyncio.sleep(random_sleep_time)

        deleted = 0
        while True:
            containers = await self.current_page.locator("div.relative").all()
            deleted_any = False

            for c in containers:
                main_btn = c.locator("button.inline-flex").first
                if await main_btn.count() == 0:
                    continue

                aria = await main_btn.get_attribute("aria-label")
                if aria and "Search chat history" in aria:
                    continue

                await main_btn.click()
                await asyncio.sleep(random_sleep_time)

                menu_btn = c.locator("button[id^='radix-']").first
                if await menu_btn.count() > 0:
                    await menu_btn.click()
                    await asyncio.sleep(random_sleep_time)
                    await self.current_page.locator(
                        "div[role='menuitem']", has_text="Delete"
                    ).first.click()
                    with suppress(Exception):
                        await self.current_page.get_by_role("button", name="Delete").click()

                deleted_any = True
                deleted += 1
                self.logger.success("Chat successfully deleted!")
                break

            if not deleted_any:
                break

        self.logger.info(f"Deleted chats: {deleted}")
        await self.stop()

    async def test_mode(self):
        await self.start_for_login()
        await self.new_page("june")
        await self.current_page.goto("https://askjune.ai/app/chat")
        input()
        await self.stop()

    # ---------------------------
    # GPT helpers
    # ---------------------------
    async def gpt_response(self, prompt):
        OPENAI_API_KEY = CONFIG.OPENAI_API_KEY
        message = ""

        try:
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
        except Exception as e:
            self.logger.info(f"Error with connecting to OpenAI: {e}")
            return ""

        try:
            gpt_version = "gpt-4o-mini"
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a friendly, concise human chat partner. Reply naturally in 1–3 sentences. "
                        "And you're real human who just entered crypto very excited "
                        "(you must not to give any signs you're AI (don't respond on it))"
                        "exclude any emojis and do some errors (like skip commas and dots)"
                    )
                },
                {"role": "user", "content": str(prompt)}
            ]
            response = client.chat.completions.create(
                model=gpt_version,
                messages=messages
            )
            message = response.choices[0].message.content
            self.logger.info(f"Message: {message}")
        except Exception as e:
            self.logger.info(f"Error with connecting to GPT: {e}")

        new_message = message.strip('"')
        self.logger.success("Message successfully written!")
        return new_message

    async def gpt_generate(self):
        OPENAI_API_KEY = CONFIG.OPENAI_API_KEY
        message = ""

        try:
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
        except Exception as e:
            self.logger.info(f"Error with connecting to OpenAI: {e}")
            return ""

        try:
            gpt_version = "gpt-4o-mini"
            prompt = "Write some human-like 2-3 sentences about web3 and how to enter it, exclude any emojis and do some errors (like skip commas and dots)"
            response = client.chat.completions.create(
                model=gpt_version,
                messages=[{"role": "user", "content": prompt}]
            )
            message = response.choices[0].message.content
            self.logger.info(f"Message: {message}")
        except Exception as e:
            self.logger.info(f"Error with connecting to GPT: {e}")

        new_message = message.strip('"')
        self.logger.success("Message successfully written!")
        return new_message

    # ---------------------------
    # Chat I/O
    # ---------------------------
    async def first_message(self):
        chat_fld = self.current_page.locator('//div[1]/div[2]/main/div/div[2]/div[2]/form/div')
        await chat_fld.click()

        input_fld = self.current_page.locator('//div[1]/div[2]/main/div/div[2]/div[2]/form/div/textarea')
        await input_fld.click()
        await input_fld.type(await self.gpt_generate())

        send_btn = self.current_page.locator(
            '//div[1]/div[2]/main/div/div[2]/div[2]/form/div/div[2]/button'
        )
        await send_btn.click()

    async def write_response(self, prompt):
        chat_fld = self.current_page.locator('//div[1]/div[2]/main/div/div[2]/div[2]/form/div')
        await chat_fld.click()

        input_fld = self.current_page.locator('//div[1]/div[2]/main/div/div[2]/div[2]/form/div/textarea')
        await input_fld.click()
        await input_fld.type(prompt)

        send_btn = self.current_page.locator(
            '//div[1]/div[2]/main/div/div[2]/div[2]/form/div/div[2]/button'
        )
        await send_btn.click()

    async def read_response(self):
        try:
            locator = self.current_page.locator("div.flex.gap-2.py-4:not([data-read='1'])")
            handles = await locator.element_handles()

            new_messages = []
            for h in handles:
                text = await h.evaluate("n => n.innerText")
                norm = " ".join(text.split())

                if not norm or len(norm) < 2:
                    await h.evaluate("n => n.setAttribute('data-read','1')")
                    continue

                fp = hashlib.sha1(norm.encode('utf-8')).hexdigest()
                if fp in self._seen_hashes:
                    await h.evaluate("n => n.setAttribute('data-read','1')")
                    continue

                self._seen_hashes.add(fp)
                new_messages.append(norm)
                await h.evaluate("n => n.setAttribute('data-read','1')")

            if new_messages:
                self.logger.info(f"New replies: {len(new_messages)}")
            return new_messages
        except Exception as e:
            self.logger.info(f"read_response error: {e}")
            return []

    # ---------------------------
    # Orchestration
    # ---------------------------
    async def get_next_time(self):
        tz = ZoneInfo("Europe/Kyiv")
        now = datetime.now(tz)
        tomorrow_date = (now + timedelta(days=1)).date()
        return datetime.combine(tomorrow_date, now.time(), tzinfo=tz)

    async def daily(self):
        MAX_LOOPS = 30
        self.logger.info("Starting Daily")

        await self.start()
        await self.new_page("june")
        await self.current_page.goto("https://askjune.ai/app/chat")

        points_sel = '//div[2]/div/div[3]/div[2]/div/button/div/div[1]/div/span[2]/span[1]'
        sel_close_welcome = '//div[4]/button'
        sel_close_welcome2 = '//div[3]/button'
        sel_cookie_decline = '//*[@id="CybotCookiebotDialogBodyButtonDecline"]'
        sel_login_check = '//div[1]/div[2]/div/div[2]/div/div[3]/div[1]/div[2]/button/div'
        sel_close_cookies_2 = '//div[1]/div/div[4]/div[1]/div/div[2]/button[4]'

        with suppress(Exception):
            login_indicator = self.current_page.locator(sel_login_check)
            if not await login_indicator.is_visible():
                self.logger.info("Account not registered yet, registering...")
                await self.stop()
                await self.login_june()
                await asyncio.sleep(7)
                await self.start()
                await self.new_page("june")
                await self.current_page.goto("https://askjune.ai/app/chat")
                self.logger.info("June Opened")

        with suppress(Exception):
            await self.current_page.locator(sel_close_welcome, timeout=2000).click()
        with suppress(Exception):
            await self.current_page.locator(sel_cookie_decline, timeout=2000).click()

        await self.current_page.keyboard.press("Escape")

        with suppress(Exception):
            await self.current_page.locator(
                '//*[@id="CybotCookiebotDialogBodyButtonDecline"]', timeout=2000
            ).click()
        with suppress(Exception):
            await self.current_page.locator(sel_close_welcome, timeout=2000).click()
        with suppress(Exception):
            await self.current_page.locator(sel_close_welcome2, timeout=2000).click()
        with suppress(Exception):
            await self.current_page.locator(sel_close_cookies_2, timeout=2000).click()

        self.logger.info("Starting generating...")
        await asyncio.sleep(4)

        points_at_start = await self.current_page.locator(points_sel).inner_text()

        await self.first_message()

        for _ in range(MAX_LOOPS):
            replies = await self.read_response()

            for i, r in enumerate(replies, 1):
                self.logger.info(f"Reply #{i}: {r}")

            if any(("error" in r.lower()) or ("reached your 5-hour usage limit" in r.lower())
                   for r in replies):
                self.logger.error("Limit reached. Closing...")
                break

            if not replies:
                await asyncio.sleep(self.random_response_time)
                continue

            incoming_text = "\n\n".join(replies)
            await asyncio.sleep(self.random_response_time)

            reply = await self.gpt_response(incoming_text)

            await asyncio.sleep(self.random_response_time)
            await self.write_response(reply)

            await asyncio.sleep(self.random_response_time)

        points_at_end = await self.current_page.locator(points_sel).inner_text()
        try:
            gained = int(points_at_end) - int(points_at_start)
        except Exception:
            gained = 0

        self.logger.info(f"You have earned {gained} points this session")
        self.logger.info(
            f"You'll be eligible to launch soft: {await self.get_next_time()} (Kyiv)"
        )

    async def run(self):
        pass

    async def setup_mails(self):
        classs = MailSetup(session=self.session, db_manager=self.db_manager, client=self.client)
        code = await classs.run()
        return code
