from utils.router import MainRouter, DbRouter


class SoftRouter(MainRouter, DbRouter):
    def get_choices(self):
        return ['Daily', 
                'Setup emails', 
                'Read points on ALL accs',
                'Delete All Chats', 
                'Test Mode (for unwinned)']

    def route(self, task, action):
        return dict(zip(self.get_choices(), [task.daily,
                                             task.setup_mails, 
                                             task.read_points,
                                             task.delete_chats, 
                                             task.test_mode
                                             ]))[action]

    @property
    def action(self):
        self.start_db_router()
        return self.get_action()

