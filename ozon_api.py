import json
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OZON_API_URL = "https://api-seller.ozon.ru"
HEADERS = {
    "Client-Id": "2403648",
    "Api-Key": "26e4c03f-593f-46dc-8efd-ab4e15eba967",
    "Content-Type": "application/json"
}

def get_product_ids():
    url = "https://api-seller.ozon.ru/v3/product/list"
    payload = {"filter": {"visibility": "ALL"}, "limit": 100, "offset": 0}
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        response.raise_for_status()
        data = response.json()
        items = data.get("result", {}).get("items", [])
        product_ids = [item["product_id"] for item in items]
        logger.info(f"Получено {len(product_ids)} товаров с Ozon")
        return product_ids
    except Exception as e:
        logger.error(f"Ошибка при получении product_ids: {e}")
        return []

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
        items = data.get("result", {}).get("items")
        if items is None:
            items = data.get("items", [])
        logger.info(f"Разбор товаров: найдено {len(items)} элементов")
        return parse_products(items)
    except Exception as e:
        logger.error(f"Ошибка получения товаров: {e}")
        return []

def parse_products(items):
    parsed = []
    for item in items:
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

        # Остатки
        stocks_data = item.get("stocks", {})
        if isinstance(stocks_data, dict):
            stocks_list = stocks_data.get("stocks", [])
        else:
            stocks_list = stocks_data if isinstance(stocks_data, list) else []
        for s in stocks_list:
            if isinstance(s, dict):
                source = s.get("source")
                if source == "fbo":
                    source = "Озон"
                elif source == "fbs":
                    source = "Свои склады"
                product["stocks"].append({
                    "source": source,
                    "present": s.get("present"),
                    "reserved": s.get("reserved")
                })

        # --- ИЗОБРАЖЕНИЯ: правильный сбор с primary_image ---
        all_images = []

        # 1. primary_image (может быть строка, словарь или список)
        primary = item.get("primary_image")
        if primary:
            if isinstance(primary, list):
                # берём первый элемент списка
                if primary and isinstance(primary[0], str):
                    all_images.append(primary[0].strip())
                elif primary and isinstance(primary[0], dict):
                    url = primary[0].get("url")
                    if url:
                        all_images.append(url.strip())
            elif isinstance(primary, str):
                all_images.append(primary.strip())
            elif isinstance(primary, dict):
                url = primary.get("url")
                if url:
                    all_images.append(url.strip())

        # 2. Массив images
        imgs = item.get("images", [])
        if isinstance(imgs, list):
            for img in imgs:
                if isinstance(img, dict):
                    url = img.get("url")
                    if url and isinstance(url, str):
                        all_images.append(url.strip())
                elif isinstance(img, str):
                    all_images.append(img.strip())
        elif isinstance(imgs, str):
            all_images.append(imgs.strip())

        # 3. Fallback (если ничего нет)
        if not all_images:
            fallback = item.get("image")
            if fallback and isinstance(fallback, str):
                all_images.append(fallback.strip())

        # Удаляем дубли, сохраняя порядок (первый – primary)
        seen = set()
        unique = []
        for img in all_images:
            if img and img not in seen:
                seen.add(img)
                unique.append(img)

        product["images"] = unique

        # Логи для отладки
        logger.info(f"Товар {product['id']}: итоговый список изображений ({len(unique)} шт.): {unique[:3]}...")

        parsed.append(product)
    return parsed
