import os
import asyncio
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from utils.client import Client
from utils.utils import Logger
from .config import CONFIG
from .browser_utils import get_random_user_agent, get_random_timezone
from .paths import PSWDS, EMAILS


class MailSetup(Logger):
    def __init__(self, session, client, db_manager):
        self.session = session
        self.client = client
        self.db_manager = db_manager
        super().__init__(self.client.address, additional={'pk': self.client.key,
                                                          'proxy': self.session.proxies.get('http')})
        self.playwright = None
        self.context = None
        self.pages = {}
        self.current_page = None

    # -------------------- infra --------------------

    async def start(self):
        self.playwright = await async_playwright().start()

        proxy_url = self.session.proxies.get('http') if self.session and self.session.proxies else None
        prep_proxy = None
        if proxy_url:
            p = urlparse(proxy_url if '://' in proxy_url else f'http://{proxy_url}')
            prep_proxy = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
            if p.username and p.password:
                prep_proxy["username"] = p.username
                prep_proxy["password"] = p.password

        user_agent, _chrome_version = get_random_user_agent()  # ожидается (ua, version)
        tz = get_random_timezone() or "Europe/Prague"
        user_data_dir = f'./browsers_data/{self.client.address}_email_data'

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,                 # на сервере чаще True
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-setuid-sandbox",
                "--ignore-certificate-errors",
            ],
            user_agent=user_agent,
            proxy=prep_proxy,
            java_script_enabled=True,
            locale="en-US",
            timezone_id=tz,
        )

        self.context.set_default_timeout(45_000)
        self.context.set_default_navigation_timeout(90_000)

        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)


    async def stop(self):
        if self.context:
            await self.context.close()
            self.context = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None


    async def new_page(self, name: str):
        if not self.context:
            raise RuntimeError("Call start() before new_page().")
        page = await self.context.new_page()
        self.pages[name] = page
        self.current_page = page
        return page


    def switch_page(self, name: str):
        if name in self.pages:
            self.current_page = self.pages[name]
        else:
            raise ValueError("Page not found")


    # -------------------- helpers --------------------

    async def _check_connectivity(self) -> bool:
        p = await self.context.new_page()
        try:
            resp = await p.goto("https://httpbin.org/ip", wait_until="domcontentloaded", timeout=20_000)
            return bool(resp and resp.ok)
        finally:
            await p.close()

    # -------------------- Gmail flow --------------------

    async def login_gmail(self, page, email: str, password: str):
        await page.goto("https://accounts.google.com/", wait_until="domcontentloaded", timeout=90_000)

        await page.fill('input[type="email"], #identifierId', email)
        await page.click('#identifierNext button, #identifierNext div[role="button"]')

        await page.wait_for_selector('input[type="password"]', timeout=60_000)
        await page.fill('input[type="password"]', password)
        await page.click('#passwordNext button, #passwordNext div[role="button"]')

        try:
            await page.wait_for_url("**/mail/**", timeout=30_000)
        except PWTimeout:
            await page.goto("https://mail.google.com/", wait_until="domcontentloaded", timeout=90_000)

        await page.wait_for_selector('div[role="main"]', timeout=60_000)


    async def list_inbox_rows(self, page, limit=10):
        rows = page.locator('tr.zA')
        await rows.first.wait_for(timeout=60_000)

        count = min(limit, await rows.count())
        items = []
        for i in range(count):
            r = rows.nth(i)
            sender = (await r.locator('span.yP, span.zF').first.inner_text()).strip()
            subject = (await r.locator('span.bog').first.inner_text()).strip()
            snippet = (await r.locator('span.y2').first.inner_text()).strip(" \u00A0-")
            date_text = ""
            try:
                date_text = (await r.locator('td.xW span, td.xW').first.inner_text()).strip()
            except Exception:
                pass
            items.append({"index": i, "sender": sender, "subject": subject, "snippet": snippet, "date": date_text})
        return items


    async def open_and_read(self, page, row_index=0):
        rows = page.locator('tr.zA')
        await rows.nth(row_index).click()

        subject = await page.locator('h2.hP, h2[role="heading"]').first.inner_text()
        subject = subject.strip()

        body = ""
        candidates = [
            'div.a3s.aiL',                        
            'div.a3s',                            
            'div[role="listitem"] div[dir="ltr"]' 
        ]
        for sel in candidates:
            loc = page.locator(sel).first
            try:
                body = (await loc.inner_text()).strip()
                if body:
                    break
            except Exception:
                continue

        return {"subject": subject, "body": body}

    # -------------------- entrypoint --------------------

    async def run(self):
        await self.start()
        try:
            ok = await self._check_connectivity()
            if not ok:
                raise RuntimeError("Network/proxy check failed (httpbin). Something wront with proxy")

            page = await self.new_page("gmail")

            if not self.client.email or not self.client.email_pswd:
                raise RuntimeError("Emails.txt or Pswds.txt are empty")

            try:
                await page.goto("https://mail.google.com/", wait_until="domcontentloaded", timeout=90_000)
                await page.wait_for_selector('div[role="main"]', timeout=10_000)
            except PWTimeout:
                await self.login_gmail(page, self.client.email, self.client.email_pswd)

            await page.goto("https://mail.google.com/", wait_until="domcontentloaded", timeout=90_000)

            inbox = await self.list_inbox_rows(page, limit=10)

            if inbox:
                opened = await self.open_and_read(page, row_index=inbox[0]["index"])

                msg = opened['subject'].split()[0]

                # self.logger.info(f"Code: {msg}")

                return msg

            await asyncio.Event().wait()

        finally:
            await self.stop()
