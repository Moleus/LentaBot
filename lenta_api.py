import requests
from bs4 import BeautifulSoup
import json


def get_json_from_url(url, headers):
    """
    For self.stores_dict and self.cities_dict jsons
    """
    with requests.Session() as s:
        text_data = s.get(url, headers=headers).text
        data = json.loads(text_data)
    return data


def get_response(url, headers):
    """
    Requests a page by given url.
    Returns: html page in text format.
    """
    session = requests.Session()
    response = session.get(url, headers=headers)
    return response


# parse html page text
def fetch_good_info(page_text):
    """
    Parses html and gets good info.
    Returns Good name, price(with promocard),
    promo state, promo period(с 23.03 по 01.04)
    """
    print(page_text)
    soup = BeautifulSoup(page_text, 'html.parser')
    good_info_container = soup.find("div", class_="sku-page-control-container sku-page__control")
    good_info = good_info_container.attrs.get("data-model")

    price = int(json.loads(good_info)['cardPrice']['integerPart'])
    title = json.loads(good_info)['title']
    isPromoForCardPrice = json.loads(good_info)['isPromoForCardPrice']
    if isPromoForCardPrice:
        promoStart = "".join(json.loads(good_info)['promoStart'][5:10].replace("-", "."))
        promoEnd = "".join(json.loads(good_info)['promoEnd'][5:10].replace("-", "."))
        promoDate = "с %s по %s" % (promoStart, promoEnd)
    else:
        promoDate = ""

    return {"title": title, "price": price, "isPromoForCardPrice": isPromoForCardPrice, "promoDate": promoDate}
