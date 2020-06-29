#!/usr/bin/env python
# -*- coding: utf-8 -*-


# Bot's work modules
import replies    # send cliched message to a user.
import filesoper  # save/load operations with files.
import lenta_api  # requests to lenta.com 

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

import threading
import itertools
import time

from dotenv import load_dotenv   # for passing telegram token from .env
load_dotenv()


SITE_WHITELIST = [
    'https://lenta.com/catalog/'
]
USE_PROXY = False
CHECK_PRICE_PERIOD = 300  # minutes
CITY, TYPE_STORE_NAME, CHOOSE_STORE, CHOICE_FIN = range(4)
GOOD_LIST, DELGOOD = range(2)

#  log messages format
logFormatter = logging.Formatter("%(asctime)s - [%(threadName)-12.12s] - [%(levelname)-5.5s] - %(message)s")
logger = logging.getLogger()

# logging level ('INFO', 'DEBUG', 'WARNING', 'ERROR', 'CRITICAL/FATAL')
logger.setLevel('DEBUG')

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


class LentaBot:
    """
    Allows you to track discounts on different goods by sending them to this bot.
    """

    # Put your telegram token in .env file
    TOKEN = os.environ.get('TELEGRAM_API_TOKEN')

    def __init__(self):
        print("\033[92m LentaBot started \033[0m")

        PROXY_URL = None
        if USE_PROXY:
            PROXY_URL = {'proxy_url': 'socks5h://192.168.1.114:9050/'}    # use proxy if tg is blocked in your country.

        updater = Updater(self.TOKEN,
                          request_kwargs=PROXY_URL,
                          use_context=True)

        CITIES_URL = "https://lenta.com/api/v1/cities"
        STORES_URL = "https://lenta.com/api/v1/stores"
        self.HEADERS = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36"
        }
        self.stores_dict = []
        self.cities_dict = []
        while self.stores_dict == [] and self.cities_dict == []:  # if site is updating, so we can't get the cities or stores.
            self.stores_dict = lenta_api.get_json_from_url(STORES_URL, self.HEADERS)
            self.cities_dict = lenta_api.get_json_from_url(CITIES_URL, self.HEADERS)
            time.sleep(5)

        self.GOODS_PER_MESSAGE = 5  # amount of customer's goods shows in one message.
        self.GOODS_DATA_LOCATION = './goods_data.json'
        self.USERS_STORES_LOCATION = './users_stores.json'

        self.user_pos = {}
        self.first_time = True

        self.json_goods_data = filesoper.read_json(self.GOODS_DATA_LOCATION)
        self.users_stores = filesoper.read_json(self.USERS_STORES_LOCATION)

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
            entry_points=[CommandHandler(['start', 'choose_store'], self.type_city_request)],
            states={
                CITY:            [MessageHandler(Filters.text, self.check_city_req)],
                TYPE_STORE_NAME: [CallbackQueryHandler(self.type_store_request)],
                CHOOSE_STORE:    [MessageHandler(Filters.text, self.check_store_req)],
                CHOICE_FIN:      [CallbackQueryHandler(self.choose_end, pattern="^" + "\d{4}" + "$")]
            },
            fallbacks=[CommandHandler('choose_store', self.type_city_request)]
        )

        dp.add_handler(CommandHandler('help', replies.manual_msg))
        dp.add_handler(CommandHandler('my_store', self.check_user_store))

        dp.add_handler(store_handler)
        dp.add_handler(good_handler)

        dp.add_handler(MessageHandler(Filters.text, self.main))

        # dp.add_error_handler(self.error)
        updater.start_polling()
        updater.idle()

    # inline keyboard
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


    # city/store choose
    def type_city_request(self, update, context):
        context.bot.send_message(
            update.message.chat_id,
            text="В каком Вы городе?",
        )
        return CITY

    # city/store choose (search req in dict)
    def search_requested(self, required_place, places_dict):
        """
        Search a city or a store by typing it's name or it's short form.
        required_place: (string) 'Санкт-Петербург' or 'Сан' or 'Выборгский р-н'
        places_dict: (dict)
            {"id":"spb",
             "name":"Санкт-Петербург",
             "lat":59.939095,
             "long":30.315868,
             "mediumStoreConcentration":true,
             "highStoreConcentration":true
            }...
        """
        logger.debug("search_requested: required_place is %s", required_place)
        relevant_places = {}
        for num, city in enumerate(places_dict):
            if required_place.lower() in places_dict[num]['name'].lower():
                relevant_places.update({num: places_dict[num]})
        return relevant_places

    # city/store choose
    def check_city_req(self, update, context):
        message_text = update.message.text
        logger.info("kearch_city: message_text is %s", message_text)
        required_cities = self.search_requested(message_text, self.cities_dict)
        if not required_cities:
            replies.request_not_found_msg(update, context)
            return ConversationHandler.END

        self.choose_city(update, context, required_cities)
        return TYPE_STORE_NAME

    # city/store choose (inline)
    def choose_city(self, update, context, cities_dict=None):
        """
        Buttons with option to choose your city from list.
        """
        cities_dict = cities_dict if cities_dict else self.cities_dict
        # logger.info("choose city: cities_dict is %s", cities_dict)
        # logger.info("choose city: %s %s", "message is", update.message.text)
        button_list = []
        for city in cities_dict:
            logger.info("choose city: %s", city)
            logger.info("choose city: CITIES: %s", cities_dict[city])
            name = cities_dict[city]["name"]
            short_name = cities_dict[city]["id"]
            button_list.append(InlineKeyboardButton(name, callback_data="store " + short_name))

        # query = update.callback_query
        reply_markup = InlineKeyboardMarkup(self.build_menu(button_list, n_cols=3))
        update.message.reply_text('Выбирите город', reply_markup=reply_markup)

    # city/store choose
    def type_store_request(self, update, context):
        query = update.callback_query
        logger.info("type store request")
        context.bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text="На какой улице Ваш магазин?",
        )
        return CHOOSE_STORE

    # city/store choose
    def check_store_req(self, update, context):
        message_text = update.message.text
        required_stores = self.search_requested(message_text, self.stores_dict)
        if not required_stores:
            replies.request_not_found_msg(update, context)
            return ConversationHandler.END

        self.choose_store(update, context, required_stores)
        return CHOICE_FIN

    # city/store choose
    def choose_store(self, update, context, stores_dict=None):
        """
        Buttons with option to choose your store from list.
        """
        stores_dict = stores_dict if stores_dict else self.stores_dict
        button_list = []

        for store in stores_dict:
            name = stores_dict[store]["name"]
            store_id = stores_dict[store]["id"]
            button_list.append(InlineKeyboardButton(name, callback_data=store_id))

        reply_markup = InlineKeyboardMarkup(self.build_menu(button_list, n_cols=3))

        context.bot.send_message(
            chat_id=update.message.chat_id,
            text="Выбирите магазин.",
            reply_markup=reply_markup
        )

    # city/store choose
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

        self.users_stores = {query.message.chat_id: [query.data, store_name]}
        filesoper.write_json(self.users_stores, self.USERS_STORES_LOCATION)

        bot = context.bot
        bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text="Ваш магазин '%s'\nСкиньте ссылку на товар" % store_name
        )
        return ConversationHandler.END


    # user's goods inline
    def back_arrow(self, update, context):
        """
        Create back arrow buton.
        """
        query = update.callback_query
        user_id = query.message.chat_id
        new_pos = self.user_pos[user_id] - self.GOODS_PER_MESSAGE

        if new_pos >= 0:
            self.user_pos[user_id] = new_pos
        else:
            self.user_pos[user_id] = 0

        self.send_user_goods(update, context)

    # user's goods inline
    def forward_arrow(self, update, context):
        """
        Create forward arrow buton.
        """
        query = update.callback_query
        user_id = query.message.chat_id
        new_pos = self.user_pos[user_id] + self.GOODS_PER_MESSAGE
        if len(self.json_goods_data[user_id]) > new_pos:
            self.user_pos[user_id] = new_pos
        self.send_user_goods(update, context)

    # user's goods inline
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

    # user's goods inline
    def create_inline_del_buttons(self, update, context):
        """
        Create crosses in the bottom of inline keyboard.
        Link them to their goods.
        Return: [list] InlineKeyboard
        """
        query = update.callback_query
        if query is not None:
            user_id = query.message.chat_id
        else:
            user_id = update.message.chat_id
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

    # user's goods inline
    def goods_text(self, update, context):
        """
        Creates text from goods' names, links, and their amount.
        """
        query = update.callback_query
        if query is not None:
            user_id = query.message.chat_id
        else:
            user_id = update.message.chat_id
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

    # user's goods inline
    def create_goods_keyboard(self, update, context):
        """
        Combine delete buttons, arrow buttons, and text
        """
        del_buttons = self.build_menu(self.create_inline_del_buttons(update, context), n_cols=5)
        del_buttons.append(self.make_arrows_list(update, context))
        reply_markup = InlineKeyboardMarkup(del_buttons)
        return reply_markup

    # user's goods inline
    def send_user_goods(self, update, context):
        """
        When /goods command received.
        Send inline keyboard with user's goods.
        """
        query = update.callback_query

        if query is not None:
            user_id = query.message.chat_id
        else:
            user_id = update.message.chat_id
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
                                              message_id=query.message.message_id,
                                              reply_markup=reply_markup,
                                              disable_web_page_preview=True,
                                              parse_mode='HTML')
            except telegram.error.BadRequest:  # if there is no message to edit
                context.bot.answer_callback_query(update.callback_query.id,
                                                  text="there's no {} page.".format(query.data))
        return GOOD_LIST

    # user's goods inline
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

    # user's goods inline
    def handle_back_to_list(self, update, context):
        """
        Go back to goods list with inline keyboard after deletion a good.
        """
        self.send_user_goods(update, context)
        return GOOD_LIST

    # user's goods inline
    def handle_del_good(self, update, context):
        """
        Deleting good from json_goods_data.
        After delete confirmation.
        """
        query = update.callback_query
        user_id = query.message.chat_id

        url_part = query.data
        for url in self.json_goods_data[user_id]:
            if url_part in url:
                del self.json_goods_data[user_id][url]
                filesoper.write_json(self.json_goods_data, self.GOODS_DATA_LOCATION)
                break

        self.send_user_goods(update, context)
        return GOOD_LIST

    # user's goods inline
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

    # check store.
    def check_user_store(self, update, context):
        """ Check your current store name """

        if update.message.chat_id not in self.users_stores:
            store = "Не определён. Выберите его /choose_store"
        else:
            store = self.users_stores[update.message.chat_id][1]  # get store name from dict
        text = "Ваш магазин - %s" % (store)
        context.bot.send_message(update.message.chat_id, text=text)

    # url append store num
    def add_store_in_url(self, user_id, url):
        """
        Removes storeId from url if exists.
        Place user's store in the end of the url.
        """

        clear_url = url.rsplit('?', 1)[0]
        store_id = self.users_stores.get(user_id, ["0005"])[0]  # get store id
        url_with_store_id = clear_url + "?StoreId=" + store_id
        return url_with_store_id

    # change goods info
    def update_goods_data(self, user_id, url, good_info, repeatNotif=True):
        """
        Save current good info (or updates it's state) in self.json_goods_data
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


    # check discounts interval decorator.
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

    @setInterval(CHECK_PRICE_PERIOD * 60)  # seconds *  60(minutes)
    def check_discount_cycle(self, context):
        for user_id, url in self.iter_goods():
            new_good_info = self.get_new_good_info(url)
            if new_good_info == "not_available":
                break
            if new_good_info == "not_found":
                self.good_not_found(context, user_id, url)
                break

            if self.check_discount(new_good_info):
                if self.check_discount_relevance(user_id, url):
                    self.new_discount(user_id, url, new_good_info)
                else:
                    self.old_discount(user_id, url, new_good_info)

    def iter_goods(self):
        for user_id in list(self.json_goods_data.keys()):
            for url in list(self.json_goods_data[user_id].keys()):
                yield user_id, url

    def get_new_good_info(self, url):
        response = lenta_api.get_response(url, self.HEADERS)
        response_status = response.status_code
        response_text = response.text
        logger.debug("response_status: %d ", response_status)
        if response_status == 502 or response_status == 500:
            return "not_available"
        elif response_status == 404:
            return "not_found"
        return lenta_api.fetch_good_info(response_text)

    def check_discount_relevance(self, user_id, url):
        repeatNotif = self.json_goods_data[user_id][url]["repeatNotif"]
        # prev_isPromoForCardPrice = self.json_goods_data[user_id][url]["isPromoForCardPrice"]
        return repeatNotif

    # check discounts
    def check_discount(self, new_good_info):
        """
        Checks every good for every user.
        Sends message if disount is found.
        Toggles the isPromoForCardPrice and repeatNotif flags.
        """
        if new_good_info:
            isPromoForCardPrice = new_good_info["isPromoForCardPrice"]
            if isPromoForCardPrice:  # disount avaliable
                return True

    def new_discount(self, context, user_id, url, new_good_info):
        self.update_goods_data(user_id, url, new_good_info, repeatNotif=False)
        filesoper.write_json(self.json_goods_data, self.GOODS_DATA_LOCATION)
        title = new_good_info['title']
        price = new_good_info['price']
        promoDate = new_good_info['pomoDate']
        try:
            replies.new_discount_msg(context, user_id, title, price, promoDate)
        except telegram.error.BadRequest:
            logger.error("The User has blocked the Bot!")

    def old_discount(self, user_id, url, new_good_info):
        self.update_goods_data(user_id, url, new_good_info, repeatNotif=True)
        filesoper.write_json(self.json_goods_data, self.GOODS_DATA_LOCATION)

    def good_not_found(self, context, user_id, url):
        good_title = self.json_goods_data[user_id][url]["title"]
        not_fount_phrase = ". Ссылка на товар больше не действительна!"
        if not_fount_phrase in good_title:  # already notified about this issue.
            return
        replies.good_not_found_msg(context, user_id, good_title)
        losted_good_info = {"title": good_title + not_fount_phrase, "price": 0, "promoDate": "", "isPromoForCardPrice": False}
        self.update_goods_data(user_id, url, losted_good_info)
        filesoper.write_json(self.json_goods_data, self.GOODS_DATA_LOCATION)

    def main(self, update, context):
        """
        Handles every text message.
        Checks if it's a link to Lenta's catalog.
        Saves this link and good info.
        """
        url = update.message.text
        user_id = update.message.chat_id

        if self.first_time is True:
            self.first_time = False
            # logger.debug(self.json_goods_data)
            self.check_discount_cycle(context)

        if not url.startswith(SITE_WHITELIST[0]):
            replies.not_valid_msg(update, context)
            return

        if (user_id in self.json_goods_data) and (url in self.json_goods_data[user_id]):
            context.bot.send_message(update.message.chat_id, text="Данный товар уже добавлен в список желаемых")
            return

        url = self.add_store_in_url(user_id, url)
        good_info = self.get_new_good_info(url)
        if not good_info:
            replies.not_valid_msg(update, context)
            return
        self.update_goods_data(user_id, url, good_info)
        filesoper.write_json(self.json_goods_data, self.GOODS_DATA_LOCATION)

        context.bot.send_message(update.message.chat_id, text="%s по цене %s руб добавлено" % (good_info["title"], good_info["price"]))

    def error(self, update, context):
        """
        Error handler.
        """
        logger.error('Update "%s" caused error "%s"' % (update, context.error))


if __name__ == '__main__':
    Bot = LentaBot()
