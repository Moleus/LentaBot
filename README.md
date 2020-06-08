# Telegram Bot for tracking discounts in Lenta.
This Bot was created to help people with tracking disounts for their favourite goods in [Lenta Catalog](https://lenta.com/catalog/).

## Install
1. Clone this repo `git clone https://github.com/Moleus/LentaBot`.
2. Install the requirements `pip3 install -r requirements.txt`.
3. Create .env file and put your Telegram Bot TOKEN there.
4. Run the Bot `python3 Bot.py`

## Usage
I. Basic
   1. Choose your city and store: `/choose_store`
   2. Go to [Lenta Catalog site](https://lenta.com/catalog/).
   3. Choose a good you like and copy it's url. For example, [appples](https://lenta.com/catalog/frukty-i-ovoshchi/frukty/yabloki/yabloki-golden-fas-ves-1kg/).
   4. Send this url to the Bot.
   5. What until a discount appears. Bot will send you a message about that.
   **Note:** Bot parses pages every 4 hours, but you can change this period in the begining of the *Bot.py* file.

II. Interacting with tracked goods.
   1. You can look at tracked goods using command `/goods`.
   2. If you want to remove a good from your tracking list - press on a cross with a good's number.

## License
MIT © Moleus
