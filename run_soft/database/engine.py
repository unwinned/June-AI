from database.engine import DbManager
from sqlalchemy import select, Boolean, func
from utils.client import Client
from utils.models import Proxy
from run_soft.paths import EMAILS, PSWDS
import os


class SoftDbManager(DbManager):
    def __init__(self, db_path, base):
        super().__init__(db_path, base)

    async def create_base_note(self, pk, proxy):
        emails = [ln.strip() for ln in open(EMAILS, encoding="utf-8") if ln.strip()] if os.path.exists(EMAILS) else []
        pswds  = [ln.strip() for ln in open(PSWDS,  encoding="utf-8") if ln.strip()] if os.path.exists(PSWDS) else []
    
        count = await self.session.scalar(select(func.count()).select_from(self.base))
        idx = int(count)
    
        email = emails[idx] if idx < len(emails) else None
        pswd  = pswds[idx] if idx < len(pswds) else None
        if not email or not pswd:
            raise RuntimeError(f"Нет email/пароля в файлах для индекса {idx}")
        

        await super().create_base_note(
            pk=pk,
            proxy=proxy,
            email=email,
            email_password=pswd,
        )


    async def get_run_data(self):
        async with self.session.begin():
            result = await self.session.execute(select(self.base))
            users = result.scalars().all()

        rows = []
        for user in users:
            client = Client(user.private_key)
            client.email = user.email
            client.email_pswd = user.email_password
            rows.append({
                'client': client,
                'proxy': Proxy(user.proxy),
            })
        return rows