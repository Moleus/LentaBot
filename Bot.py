#!/usr/bin/env python
# -*- coding: utf-8 -*-


import os
import telegram
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    ConversationHandler
)
from telegram.error import Unauthorized
import logging

import requests
from bs4 import BeautifulSoup
import json

import threading
import itertools
import re

from dotenv import load_dotenv   # for passing telegram token from .env
load_dotenv()

SITE_WHITELIST = [
    'https://lenta.com/catalog/'
]

USE_PROXY = True
CHECK_PRICE_PERIOD = 500  # minutes
CITY, STORE = range(2)
GOOD_LIST, DELGOOD = range(2)

#  log messages format
logFormatter = logging.Formatter("%(asctime)s \
                                 [%(threadName)-12.12s] \
                                 [%(levelname)-5.5s] \
                                 %(messages)")
logger = logging.getLogger()

# logging level. ('INFO', 'DEBUG', 'WARNING', 'ERROR', 'CRITICAL/FATAL')
logger.setLevel('INFO')

# save logs in ./logs dir.
if not os.path.isdir('./logs'):
    os.mkdir('logs')
fileHandler = logging.FileHandler("{0}/{1}.log".format("logs", "lentaBot"))
fileHandler.setFormatter(logFormatter)
logger.addHandler(fileHandler)

# echo logs in console
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)


class LentaBot():
    """
    Allows you to track sales on different goods by sending them to this bot.
    """

    # Put your telegram token in .env file
    TOKEN = os.environ.get('TELEGRAM_API_TOKEN')

    def __init__(self):
        print("LentaBot started")
        
        PROXY_URL = None
        if USE_PROXY:
            PROXY_URL = {'proxy_url': 'socks5h://192.168.1.114:9050/'}    # use proxy if tg is blocked in your country.

        updater = Updater(self.TOKEN,
                          request_kwargs=PROXY_URL,
                          use_context=True)

        stores_url = "https://lenta.com/api/v1/stores"
        cities_url = "https://lenta.com/api/v1/cities"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36"
        }
        self.cities = self.get_json_from_url(cities_url)
        self.stores = self.get_json_from_url(stores_url)

        self.GOODS_PER_MESSAGE = 5  # amount of customer's goods shows in one message.

        self.user_pos = {}
        self.first_time = True

        if os.path.isfile('./good_urls.json'):
            with open("good_urls.json", "r") as f:
                self.json_goods_data = json.load(f)
        else:
            self.json_goods_data = {}

        if os.path.isfile('./users_stores.json'):
            with open("users_stores.json", "r") as f:
                self.users_stores = json.load(f)
        else:
            self.users_stores = {}


        dp = updater.dispatcher

        good_handler = ConversationHandler(
            [CommandHandler('goods', self.send_user_goods)], {
                GOOD_LIST: [
                    CallbackQueryHandler(self.forward_arrow, pattern="^" + "next" + "$"),
                    CallbackQueryHandler(self.back_arrow, pattern="^" + "previous" + "$"),
                    CallbackQueryHandler(self.good_handler_end, pattern="^" + "exit" + "$"),
                    CallbackQueryHandler(self.confirm_del_action_keyboard, pattern="^" + "[0-9]|[a-z]*" + "-")
                ],
                DELGOOD: [
                    CallbackQueryHandler(self.handle_del_good, pattern="^" + "[0-9]|[a-z]*" + "-"),
                    CallbackQueryHandler(self.handle_back_to_list, pattern="cancel")
                ]
            },
            fallbacks=[CommandHandler('goods', self.send_user_goods)]
        )

        store_handler = ConversationHandler(
            entry_points=[CommandHandler(['start', 'choose_store'], self.choose_city)],
            states={
                CITY: [CallbackQueryHandler(self.choose_store, pattern="^" + "city")],
                STORE: [CallbackQueryHandler(self.choose_end, pattern="^" + "\d{4}"+"$")]
            },
            fallbacks=[CommandHandler(['start', 'choose_store'], self.choose_city)]
        )

        dp.add_handler(CommandHandler('help', self.manual))
        dp.add_handler(CommandHandler('my_store', self.check_user_store))

        dp.add_handler(store_handler)
        dp.add_handler(good_handler)

        dp.add_handler(MessageHandler(Filters.text, self.main))

        dp.add_error_handler(self.error)
        updater.start_polling()
        updater.idle()

    def manual(self, update, context):
        context.bot.send_message(update.message.chat_id,
                                 text=u'\tДля начала нужно выбрать магазин, ' \
                                 'цены которого вы собираетесь отслеживать.\n\n'
                                 '\tСкопируйте ссылку на товар из каталога ленты и вставьте сюда.\n'
                                 'Когда цена на данный товар снизится, Бот Вас уведомит об этом.')

    def get_json_from_url(self, url):
        """
        For self.stores and self.cities jsons
        """
        with requests.Session() as s:
            text_data = s.get(url, headers=self.headers).text
            data = json.loads(text_data)
        return data

    def start(self, update, context):
        """
        Startup message
        """
        context.bot.send_message(update.message.chat_id, text=u'скинь ссылку на товар\n'
                                                              'из каталога: https://lenta.com/catalog ')

    def unknown_command(self, update, context):
        """
        When user sends command which listed in handlers. See dp.add_handler.
        """
        context.bot.send_message(chat_id=update.effective_chat.id,
                                 text="Извините, такой команды не существует.\n \
                                 Посмотрите список существующих команд")

    def build_menu(self, buttons, n_cols, header_buttons=None, footer_buttons=None):
        """
        pattern for creating buttons grid.
        """
        menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
        if header_buttons:
            menu.insert(0, [header_buttons])
        if footer_buttons:
            menu.append([footer_buttons])
        return menu

    def choose_city(self, update, context):
        """
        Buttons with option to choose your city from list.
        """
        button_list = []
        for num, city in enumerate(self.cities):
            name = city["name"]
            short_name = city["id"]
            button_list.append(InlineKeyboardButton(name, callback_data="city " + short_name))

        reply_markup = InlineKeyboardMarkup(self.build_menu(button_list, n_cols=3))
        update.message.reply_text('Choose city:', reply_markup=reply_markup)
        return CITY

    def choose_store(self, update, context):
        """
        Buttons with option to choose your store from list.
        """
        query = update.callback_query
        button_list = []

        for store in self.stores:
            name = store["name"]
            store_id = store["id"]
            store_key = store["cityKey"]

            callback_city = query.data
            if store_key == callback_city.split(" ")[1]:
                button_list.append(InlineKeyboardButton(name, callback_data=store_id))

        reply_markup = InlineKeyboardMarkup(self.build_menu(button_list, n_cols=3))

        context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text="Choose store",
            reply_markup=reply_markup
        )

        return STORE

    def choose_end(self, update, context):
        """
        Remove buttons after choosing a store.
        """
        query = update.callback_query

        for lists in query.message.reply_markup.inline_keyboard:
            for element in lists:
                if query.data in element['callback_data']:
                    store_name = element["text"]
                    break

        self.users_stores = {str(query.message.chat_id): [query.data, store_name]}
        self.save_users_stores()

        bot = context.bot
        bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text="Ваш магазин '%s'\nСкиньте ссылку на товар" % store_name
        )

        return ConversationHandler.END

    def save_users_stores(self):
        """
        Saves storeId and Store name from dict self.users_stores
        into users_stores.json.
        """
        with open("users_stores.json", "w") as f:
            json.dump(self.users_stores, f, ensure_ascii=False, indent=4)

    def save_json_goods_data_in_file(self):
        """
        Saves all info about goods by their appliers.
        "user1_id": {
                    url1: {
                            "title":str,
                            "price":int,
                            "isPromoForCardPrice": bool,
                            "promoDate": str,
                            "repeatNotif": bool
                            },
                    url2: {...}
        "user2_id": {...}
        """
        with open("good_urls.json", "w") as f:
            json.dump(self.json_goods_data, f, ensure_ascii=False, indent=4)

    def check_user_store(self, update, context):
        """ Check your current store name """

        if str(update.message.chat_id) not in self.users_stores:
            store = "Не определён. Выберите его /choose"
        else:
            store = self.users_stores[str(update.message.chat_id)][1]  # get store name from dict
        text = "Ваш магазин - %s" % (store)
        context.bot.send_message(update.message.chat_id, text=text)

    def setInterval(interval):
        """ decorator for periodic checking price """
        def decorator(function):
            def wrapper(*args, **kwargs):
                stopped = threading.Event()

                def loop():  # executed in another thread
                    while not stopped.wait(interval):  # until stopped
                        function(*args, **kwargs)

                t = threading.Thread(target=loop)
                t.daemon = True  # stop if the program exits
                t.start()
                return stopped
            return wrapper
        return decorator

    def add_store_in_url(self, user_id, url):
        """
        Removes storeId from url if exists.
        Place user's store in the end of the url.
        """

        clear_url = url.rsplit('?', 1)[0]
        store_id = self.users_stores.get(user_id, ["0005"])[0]  # get store id
        url_with_store_id = clear_url + "?StoreId=" + store_id
        return url_with_store_id

    def take_page_text(self, url, user_id):
        """
        Requests a page by given url.
        Returns html in text format.
        """
        session = requests.Session()
        page_text = session.get(url, headers=self.headers).text
        return page_text

    def get_new_good_info(self, page_text):
        """
        Parses html and gets good info.
        Returns Good name, price(with promocard),
        promo state, promo period(с 23.03 по 01.04)
        """
        soup = BeautifulSoup(page_text, 'html.parser')
        good_info = soup.find("div", class_="sku-page-control-container sku-page__control")
        if good_info is None:
            return None

        good_info = good_info.attrs.get("data-model")

        price = int(json.loads(good_info)['cardPrice']['integerPart'])
        title = json.loads(good_info)['title']
        isPromoForCardPrice = json.loads(good_info)['isPromoForCardPrice']
        if isPromoForCardPrice:
            promoStart = ".".join(json.loads(good_info)['promoStart'][:10].split("-")[::-1][:2])
            promoEnd = ".".join(json.loads(good_info)['promoEnd'][:10].split("-")[::-1][:2])
            promoDate = "с %s по %s" % (promoStart, promoEnd)
        else:
            promoDate = ""

        return {"title": title, "price": price, "isPromoForCardPrice": isPromoForCardPrice, "promoDate": promoDate}

    def update_goods_data(self, user_id, url, good_info, repeatNotif=True):

        """
        Save current good info in self.json_goods_data
        Calls save data in file function.
        """
        title = good_info["title"]
        price = good_info["price"]
        isPromoForCardPrice = good_info["isPromoForCardPrice"]
        promoDate = good_info["promoDate"]
        self.json_goods_data.setdefault(user_id, {})
        self.json_goods_data[user_id].update({url: {"title": title,
                                                    "price": price,
                                                    "isPromoForCardPrice": isPromoForCardPrice,
                                                    "promoDate": promoDate,
                                                    "repeatNotif": repeatNotif}})

        self.save_json_goods_data_in_file()

    def back_arrow(self, update, context):
        """
        Create back arrow buton.
        """
        query = update.callback_query
        user_id = str(query.message.chat_id)
        new_pos = self.user_pos[user_id] - self.GOODS_PER_MESSAGE

        if new_pos >= 0:
            self.user_pos[user_id] = new_pos
        else:
            self.user_pos[user_id] = 0

        self.send_user_goods(update, context)

    def forward_arrow(self, update, context):
        """
        Create forward arrow buton.
        """
        query = update.callback_query
        user_id = str(query.message.chat_id)
        new_pos = self.user_pos[user_id] + self.GOODS_PER_MESSAGE
        if len(self.json_goods_data[user_id]) > new_pos:
            self.user_pos[user_id] = new_pos
        self.send_user_goods(update, context)

    def make_arrows_list(self, update, context):
        """
        Combine arrows and exit button in inline keyboard.
        """
        left_arrow = u"\u2190"
        right_arrow = u"\u2192"
        exit_cross = "CLOSE"

        arrows_list = [InlineKeyboardButton(left_arrow, callback_data="previous"),
                       InlineKeyboardButton(exit_cross, callback_data="exit"),
                       InlineKeyboardButton(right_arrow, callback_data="next")]
        return arrows_list

    def del_buttons_list(self, update, context):
        """
        Create crosses in the bottom of inline keyboard.
        Link them to their goods.
        """
        query = update.callback_query
        if query is not None:
            user_id = str(query.message.chat_id)
        else:
            user_id = str(update.message.chat_id)
        del_buttons_list = []

        start = self.user_pos[user_id]
        end = self.user_pos[user_id] + self.GOODS_PER_MESSAGE
        sliced_dict = dict(itertools.islice(self.json_goods_data[user_id].items(), start, end))

        for num, url in enumerate(sliced_dict):
            short_name = sliced_dict[url]["title"].split(" ")[0]
            splited_name = url.rsplit("/", 2)[-2]
            splited_name = splited_name.rsplit("-")[-4:]
            url_part = "-".join(splited_name)

            num = str(num + 1)
            callback = url_part + " " + short_name
            del_buttons_list.append(InlineKeyboardButton(num + " " + u"\u274C", callback_data=callback))
        return del_buttons_list

    def goods_text(self, update, context):
        """
        Creates text from goods' names, links, and their amount.
        """
        query = update.callback_query
        if query is not None:
            user_id = str(query.message.chat_id)
        else:
            user_id = str(update.message.chat_id)
        goods_text = ""

        start = self.user_pos[user_id]
        end = self.user_pos[user_id] + self.GOODS_PER_MESSAGE

        if user_id not in self.json_goods_data.keys():
            return None

        sliced_dict = dict(itertools.islice(self.json_goods_data[user_id].items(), start, end))
        end = start + len(sliced_dict)
        title_page_text_num = "Результаты %s-%s из %s \n" % (start + 1,
                                                             end,
                                                             str(len(self.json_goods_data[user_id])))

        for num, url in enumerate(sliced_dict):
            title = self.json_goods_data[user_id][url]["title"]
            price = self.json_goods_data[user_id][url]["price"]
            promoDate = self.json_goods_data[user_id][url]["promoDate"]

            goods_text = goods_text + str(num + 1) + ". " \
                                    + '<a href=' + '"' + url + '"' + '>' + title + '</a> ' \
                                   + " тек. ц: " + str(price) + ' р. ' + promoDate + "\n"

        if goods_text == "":
            return None
        goods_text = title_page_text_num + goods_text
        return goods_text

    def create_goods_keyboard(self, update, context):
        """
        Combine delete buttons, arrow buttons, and text
        """
        del_buttons = self.build_menu(self.del_buttons_list(update, context), n_cols=5)
        del_buttons.append(self.make_arrows_list(update, context))
        reply_markup = InlineKeyboardMarkup(del_buttons)
        return reply_markup

    def send_user_goods(self, update, context):
        """
        When /goods command received.
        Send inline keyboard with user's goods.
        """
        query = update.callback_query

        if query is not None:
            user_id = str(query.message.chat_id)
        else:
            user_id = str(update.message.chat_id)
            self.user_pos[user_id] = 0

        self.user_pos.setdefault(user_id, 0)
        goods_list_text = self.goods_text(update, context)
        if goods_list_text is None:
            text = "У Вас нет отслеживаемых товаров"
            reply_markup = None
        else:
            text = self.goods_text(update, context)
            reply_markup = self.create_goods_keyboard(update, context)

        if update.message:
            update.effective_message.reply_text(text,
                                                reply_markup=reply_markup,
                                                disable_web_page_preview=True,
                                                parse_mode='HTML')

        else:
            try:
                context.bot.edit_message_text(text,
                                              chat_id=query.message.chat_id,
                                              jessage_id=query.message.message_id,
                                              reply_markup=reply_markup,
                                              disable_web_page_preview=True,
                                              parse_mode='HTML')
            except:
                context.bot.answer_callback_query(update.callback_query.id,
                                                  text="there's no {} page.".format(query.data))
        return GOOD_LIST

    def confirm_del_action_keyboard(self, update, context):
        """
        Buttons to confirm or reject deleting good from your list.

        """
        query = update.callback_query
        url_part_with_name = query.data.split(" ")
        url_part = url_part_with_name[0]
        short_name = url_part_with_name[1]

        keyboard = [[InlineKeyboardButton("Отмена", callback_data="cancel"),
                     InlineKeyboardButton("Удалить", callback_data=url_part)]]

        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.edit_message_text("Вы уверены что хотите удалить {}?".format(short_name),
                                      chat_id=query.message.chat_id,
                                      message_id=query.message.message_id,
                                      reply_markup=reply_markup)
        return DELGOOD

    def handle_back_to_list(self, update, context):
        """
        Go back to goods list with inline keyboard after deletion a good.
        """
        self.send_user_goods(update, context)
        return GOOD_LIST

    def handle_del_good(self, update, context):
        """
        Deleting good from json_goods_data.
        After delete confirmation.
        """
        query = update.callback_query
        user_id = str(query.message.chat_id)

        url_part = query.data
        for url in self.json_goods_data[user_id]:
            if url_part in url:
                del self.json_goods_data[user_id][url]
                self.save_json_goods_data_in_file()
                break

        self.send_user_goods(update, context)
        return GOOD_LIST

    def good_handler_end(self, update, context):
        """
        Replace inline keyboard and goods info with default phrase.
        """
        query = update.callback_query

        bot = context.bot
        bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id, text="скиньте ссылку на товар"
        )

        return ConversationHandler.END

    @setInterval(CHECK_PRICE_PERIOD * 60)
    def checking_for_sales(self, update, context):
        """
        Checks every good for every user.
        Sends message if sale is found.
        Toggles the isPromoForCardPrice and repeatNotif flags.
        """
        logger.info("FOR SALES")
        for user_id in list(self.json_goods_data.keys()):
            for url in list(self.json_goods_data[user_id].keys()):
                try:
                    logger.warning(url)
                    page_text = self.take_page_text(url, user_id)
                    new_good_info = self.get_new_good_info(page_text)
                    if new_good_info:
                        logger.warning(f'info block: \n {new_good_info} \n')
                        repeatNotif = self.json_goods_data[user_id][url]["repeatNotif"]
                        prev_isPromoForCardPrice = self.json_goods_data[user_id][url]["isPromoForCardPrice"]
                        isPromoForCardPrice = new_good_info["isPromoForCardPrice"]
                        if isPromoForCardPrice and repeatNotif:  # new sale avaliable
                            logger.warning("sale!!!")
                            try:
                                self.update_goods_data(user_id, url, new_good_info, repeatNotif=False)
                                context.bot.send_message(chat_id=int(user_id),
                                                         text=u"скидка на %s \n"
                                                              "Текущая цена: %s \n"
                                                              "Действительна %s" % (new_good_info["title"],
                                                                                    new_good_info["price"],
                                                                                    new_good_info["promoDate"]))
                            except telegram.error.BadRequest:
                                logger.warning("User closed messages")

                        elif isPromoForCardPrice != prev_isPromoForCardPrice and isPromoForCardPrice is False:
                            self.update_goods_data(user_id, url, new_good_info, repeatNotif=True)
                            # {"title": title, "price": price, "promoDate": "", "isPromoForCardPrice": False}

                except Exception:
                    logger.exception("message")

    def not_valid(self, update, context):
        """
        Send error message to user if url is wrong.
        """
        context.bot.send_message(update.message.chat_id, text=u'данная ссылка не является каталогом ленты\n'
                                                              'каталог: https://lenta.com/catalog')

    def main(self, update, context):
        """
        Handles every text message.
        Checks if it's a link to Lenta's catalog.
        Saves this link and good info.
        """
        url = update.message.text
        user_id = str(update.message.chat_id)

        if self.first_time is True:
            self.first_time = False
            self.checking_for_sales(update, context)

        if not url.startswith(SITE_WHITELIST[0]):
            self.not_valid(update, context)
            return

        if (user_id in self.json_goods_data) and (url in self.json_goods_data[user_id]):
            context.bot.send_message(update.message.chat_id, text="Данный товар уже добавлен в список желаемых")
            return

        url = self.add_store_in_url(user_id, url)
        page_text = self.take_page_text(url, user_id)
        good_info = self.get_new_good_info(page_text)
        if good_info is None:
            self.not_valid(update, context)
            return
        self.update_goods_data(user_id, url, good_info)

        context.bot.send_message(update.message.chat_id, text="%s по цене %s руб добавлено" % (good_info["title"], good_info["price"]))

    def error(self, update, context):
        """
        Error handler.
        """
        logger.error('Update "%s" caused error "%s"', update, context.error)


if __name__ == "__main__":
    bot = LentaBot()
