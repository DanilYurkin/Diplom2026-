import json

import requests
import logging


# http://127.0.0.1:5000/about
# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OZON_API_URL = "https://api-seller.ozon.ru"
HEADERS = {
    "Client-Id": "2403648",  # Замените на ваш Client-ID
    "Api-Key": "26e4c03f-593f-46dc-8efd-ab4e15eba967",  # Замените на ваш API-ключ
    "Content-Type": "application/json"
}


def get_product_ids():
    url = "https://api-seller.ozon.ru/v3/product/list"
    payload = {
        "filter": {
            "visibility": "ALL"
        },
        "limit": 100,
        "offset": 0
    }

    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()

        logger.info(f"Ответ от Ozon /v3/product/list: {json.dumps(data, indent=2, ensure_ascii=False)}")

        items = data.get("result", {}).get("items", [])
        product_ids = [item["product_id"] for item in items]

        logger.info(f"Получено {len(product_ids)} товаров с Ozon")
        return product_ids

    except Exception as e:
        logger.error(f"Ошибка при получении product_ids: {e}")
        return []

def get_product_list_items():
    url = "https://api-seller.ozon.ru/v3/product/list"
    payload = {
        "filter": {"visibility": "ALL"},
        "limit": 100,
        "offset": 0
    }
    response = requests.post(url, headers=HEADERS, json=payload)
    response.raise_for_status()
    data = response.json()
    return data.get("result", {}).get("items", [])


def get_products_from_ozon():
    product_ids = get_product_ids()
    if not product_ids:
        logger.error("Не получены ID товаров для запроса")
        return []

    url = f"{OZON_API_URL}/v3/product/info/list"
    payload = {"product_id": product_ids}
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()
        # **NEW**: dump the response so you can inspect it
        logger.info(f"Ответ от Ozon /v3/product/info/list: {json.dumps(data, ensure_ascii=False, indent=2)}")
        # сначала пробуем извлечь из data["result"]["items"],
        # а если такого ключа нет — то из data["items"]
        items = data.get("result", {}).get("items")
        if items is None:
            items = data.get("items", [])
        logger.info(f"Разбор товаров: найдено {len(items)} элементов")
        logger.info(f"Получено {len(items)} товаров с Ozon")
        return parse_products(items)
    except Exception as e:
        logger.error(f"Ошибка получения товаров: {e}")
        return []



def parse_products(items):
    parsed = []
    for item in items:
        # Основные поля товара
        product = {
            "id": item.get("id"),
            "offer_id": item.get("offer_id", ""),
            "name": item.get("name", ""),
            "price": float(item.get("price", 0)),
            "old_price": float(item.get("old_price", 0)),
            "currency_code": item.get("currency_code", "RUB"),
            "is_archived": item.get("is_archived", False),
            "stocks": [],
            "images": []
        }

        # Разбор остатков
        stocks_data = item.get("stocks", {})
        if isinstance(stocks_data, dict):
            stocks_list = stocks_data.get("stocks", [])
        else:
            stocks_list = stocks_data if isinstance(stocks_data, list) else []
        for s in stocks_list:
            if isinstance(s, dict):
                source = s.get("source")
                # Замена обозначений складов
                if source == "fbo":
                    source = "Озон"
                elif source == "fbs":
                    source = "Свои склады"

                product["stocks"].append({
                    "source": source,
                    "present": s.get("present"),
                    "reserved": s.get("reserved")
                })

        # Разбор изображений
        imgs = item.get("images", [])
        if isinstance(imgs, list):
            for img in imgs:
                if isinstance(img, dict) and "url" in img:
                    product["images"].append(img["url"])
                elif isinstance(img, str):
                    product["images"].append(img)
        elif isinstance(imgs, str):
            product["images"].append(imgs)

        parsed.append(product)
    return parsed