import os
import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.error import Unauthorized
import logging

import requests
from bs4 import BeautifulSoup
import json

import threading
import time 


WHITELIST = [
    'https://lenta.com/catalog/'
]


class LentaBot():

    TOKEN = os.environ.get('TELEGRAM_API_TOKEN') 
    

    def __init__(self):
        print("LentaBot started")
        updater = Updater(self.TOKEN, 
                        request_kwargs={
            'proxy_url': 'socks5://192.168.1.108:9100/',
                                
        },             use_context=True
                     )
         
        self.default_city_url = "https://lenta.com/api/v1/me/store/default"
        self.headers  = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.117 Safari/537.36"
        }
        
        self.good_by_user = {}  # by users' ids  {user_id1: {url1: primary_price, url2: primary_price}, 
                                #                {user_id2: {url1: primary_price, url2: primary_price}} 
        WAIT_TIME_SECONDS = 1 * 60 * 60

        ticker = threading.Event()
        while not ticker.wait(WAIT_TIME_SECONDS):
            self.checking_for_sales()
        
        dp = updater.dispatcher
        dp.add_handler(CommandHandler('start', self.start))
        dp.add_handler(CommandHandler('help', self.start))
        dp.add_handler(MessageHandler(Filters.text, self.main))
        dp.add_error_handler(self.error)
        updater.start_polling()
        updater.idle()
 
    def start(self, update, context):
        context.bot.send_message(update.message.chat_id, text=u'скинь ссылку на товар\
                                                    из каталога: https://lenta.com/catalog ')
    #def send_msg(self, user_id, text):
    #    context.bot.send_message(user_id, text=text)  # in plans
                  

    def take_good_info(self, url, city_url=None):
        print(url+ '\n')
        #print(self.default_city_url)
        print(self.headers)
        if city_url == None:
            city_url = self.default_city_url
        session = requests.Session() 
        session.post(city_url, headers=self.headers)
        page = session.get(url, headers=self.headers).text
        print(session.cookies.get_dict())
        #print(page.text)
        soup = BeautifulSoup(page, 'html.parser')
        print("passed2")
        info_block =soup.find("div", class_="sku-card__card-item-counter card-item-counter js-sku-card-data")
        good_info = info_block.attrs.get("data-sku") 
        price = json.loads(good_info)['cardPrice']['integerPart']
        title = json.loads(good_info)['title']
        #print(price, " !!!")
        return title, price


    def keep_or_rem_good(keep=False):
        if keep == False:
            del self.good_by_user[user_id][url]  

    def sale_found(url):
        user_id = self.good_by_user[url]
        context.bot.send_message(update.message.user_id, text=u'товар: %s .\n Текущая цена: %s' % (title, price))         


    def checking_for_sales(self):
        print("checking")
        for user_id in self.good_by_user:
            for url in self.good_by_user[user_id]:
                print(user_id[url])
                title, price = take_good_info(user_id[url])
                                
                if ((starting_price - price) / starting_price) > 0.15:
                   sale_found(url)                                         

    def main(self, update, context):
        print('main method: "%s"' % update.message.text)
        url = update.message.text
        user_id = update.message.chat_id

        if not url.startswith(WHITELIST[0]):
            context.bot.send_message(update.message.chat_id, text=u'данная ссылка не является каталогом ленты')
            return

        if url not in self.good_by_user[user_id]:        
            self.good_by_user[user_id] = self.good_by_user[user_id].append(url)
            starting_price = self.take_good_info(url)[1]
            self.good_by_user[user_id][url] = starting_price
        
        message = context.bot.send_message(update.message.chat_id, text="%s" % starting_price)
        print(message)        

    def error(self, update, context):
        logger.warning('Update "%s" caused error "%s"', update, context.error)



if __name__ == "__main__":
    bot = LentaBot()
                                         
