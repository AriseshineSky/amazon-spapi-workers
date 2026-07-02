import telegram
from telegram.ext import Updater


class TelegramBot(object):
    def __init__(self, api_token):
        self.updater = Updater(token=api_token, use_context=True)
        self.dispatcher = self.updater.dispatcher

    def send_message(self, chat_id, message):
        self.updater.bot.send_message(
            chat_id,
            message,
            parse_mode=telegram.ParseMode.HTML,
            disable_web_page_preview=True,
        )
