"""
Module with telegram bot replies to user's messages.
"""


def manual_msg(update, context):
    """
    Help message. When '/help' command is recieved.
    """
    context.bot.send_message(
        update.message.chat_id,
        text=u'\tДля начала нужно выбрать магазин, '
        'цены которого вы собираетесь отслеживать.\n\n'
        '\tСкопируйте ссылку на товар из каталога ленты и вставьте сюда.\n'
        'Когда цена на данный товар снизится, Бот Вас уведомит об этом.'
    )


def onstart_msg(update, context):
    """
    Start message. When '/start' command is recieved.
    """
    context.bot.send_message(
        update.message.chat_id, text=u'скинь ссылку на товар\n'
        'из каталога: https://lenta.com/catalog '
    )


def unknown_command_msg(update, context):
    """
    When user sends command which listed in handlers. See dp.add_handler.
    """
    context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Извините, такой команды не существует.\n \
        Посмотрите список существующих команд"
    )


def not_valid_msg(update, context):
    """
    Send error message to user if url is wrong.
    """
    context.bot.send_message(
        update.message.chat_id, text=u'данная ссылка не является каталогом ленты\n'
        'каталог: https://lenta.com/catalog'
    )


def request_not_found_msg(update, context):
    """
    Use when there're no results for city/store search.
    """
    context.bot.send_message(
        update.message.chat_id,
        text="По Вашему запросу ничего не найдено."
    )


def new_discount_msg(context, user_id, title, price, pomoDate):
    context.bot.send_message(
        chat_id=user_id,
        text=f"скидка на {title} \n"
             "Текущая цена: {price} \n"
             "Действительна {promoDate}"
    )


def good_not_found_msg(context, user_id, good_title):
    context.bot.send_message(
        chat_id=user_id,
        text=f'Не получилось открыть ссылку на товар: "{good_title}".\n'
             'Проверьте, что ссылка ещё действительна.'
    )
