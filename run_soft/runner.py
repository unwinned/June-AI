from .router import SoftRouter
from utils.runner import ModernRunner
from utils.models import RpcProviders
from utils.utils import get_session, sleep, get_data_lines, get_new_db_path_name, build_db_path
from .task import Task
from .database.engine import SoftDbManager
from .database.models import SoftBaseModel
from .config import CONFIG
import os
import random
from loguru import logger
import traceback
import asyncio
from .self_sender import SelfSender


class SoftRunner(ModernRunner):
    def __init__(self):
        self.Router = SoftRouter
        super().__init__()

    async def run_task(self, data):
        semaphore = self.global_data['semaphore']
        async with semaphore:
            async with SoftDbManager(build_db_path(self.db_name), SoftBaseModel) as db_manager:
                proxy = data['proxy']
                client = data['client']
                session = get_session('',
                                      proxy.session_proxy)
                client.define_new_provider(RpcProviders.SAHARA_TESTNET.value)
                task = Task(session=session, client=client, db_manager=db_manager)
                await sleep(*CONFIG.SETTINGS.SLEEP_BETWEEN_WALLETS)
                await self.Router().route(task=task, action=self.action)()


    def get_global_data(self):
        global_data = super().get_global_data()
        semaphore = asyncio.Semaphore(CONFIG.SETTINGS.SIMULTANEOUS_ACCOUNTS_IN_WORK)
        global_data.update({"semaphore": semaphore})
        return global_data

    async def handle_db(self):
        if self.db_name == 'new':
            new_db = get_new_db_path_name()
            async with SoftDbManager(new_db, SoftBaseModel) as db_manager:
                await db_manager.create_tables()
                async with db_manager.session.begin():
                    try:
                        for curr in range(len(self.prepared_data['clients'])):
                                data = {key: value[curr] for key, value in self.prepared_data.items()}
                                pk = data['clients'].key
                                proxy = data['proxies'].proxy
                                await db_manager.create_base_note(pk, proxy)
                    except Exception:
                        os.remove(new_db)
                        raise
            self.db_name = new_db
        async with SoftDbManager(build_db_path(self.db_name), SoftBaseModel) as db_manager:
            return await db_manager.get_run_data()

    async def prepare_db_run(self):
        await self.initialize()
        self.prepared_data = self.prepare_data()
        tasks = []
        try:
            data_list = await self.handle_db()
            random.shuffle(data_list)
        except Exception as e:
            logger.error(f'Error while handling database: {e}\n[{traceback.format_exc()}]')
            return
        logger.info(f'Running {len(data_list)} accounts...')
        if self.action.lower() == 'self-sender':
            self_sender_task = SelfSender(clients=[data['client'] for data in data_list])
            await self_sender_task.run()
        else:
            for data in data_list:
                tasks.append(asyncio.create_task(self.run_task_with_retry(data)))
            results, _ = await asyncio.wait(tasks)
            await self.after_run(results)