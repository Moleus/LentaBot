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
    Requests a reponse by given url.
    Returns: http response.
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
    soup = BeautifulSoup(page_text, 'html.parser')
    good_info_container = soup.find("div", class_="sku-page-control-container sku-page__control")
    good_info = good_info_container.attrs.get("data-model")

    price = round(json.loads(good_info)['cardPrice']['value'])
    title = json.loads(good_info)['title']
    isPromoForCardPrice = json.loads(good_info)['isPromoForCardPrice']
    if isPromoForCardPrice:
        print(json.loads(good_info)['promoStart'])
        print(json.loads(good_info)['promoEnd'])
        # promoStart
        promo_start_string = json.loads(good_info)['promoStart']
        promo_start_list = promo_start_string[5:10].split("-")
        promo_start_list.reverse()
        promo_start = ".".join(promo_start_list)
        # promoEnd
        promo_end_string = json.loads(good_info)['promoEnd']
        promo_end_list = promo_end_string[5:10].split("-")
        promo_end_list.reverse()
        promo_end = ".".join(promo_end_list)
        # promoEnd = "".join((json.loads(good_info)['promoEnd'][5:10].replace("-", ".")).reverse())
        print(promo_start)
        print(promo_end)

        promoDate = "с %s по %s" % (promo_start, promo_end)
    else:
        promoDate = ""

    return {"title": title, "price": price, "isPromoForCardPrice": isPromoForCardPrice, "promoDate": promoDate}
