import sqlite3
import requests
from bs4 import BeautifulSoup
import datetime
from typing import List, Dict, Any, Optional, Tuple

def extract_price(document: BeautifulSoup, selector: str) -> Optional[float]:
    if price_element := document.select_one(selector):
        price_text = price_element.text.strip()
        if price_text.startswith('$'):
            price_text = price_text[1:]
        price_text = price_text.replace(',', '')
        return None if price_text == '-' else float(price_text)
    return None

def get_game_prices(game_id: str) -> Dict[str, Any]:
    url = f"https://www.pricecharting.com/game/{game_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        document = BeautifulSoup(response.content, 'html.parser')

        return {
            'time': datetime.datetime.now().isoformat(),
            'game': game_id,
            'prices': {
                'complete': extract_price(document, '#complete_price > span.price.js-price'),
                'new': extract_price(document, '#new_price > span.price.js-price'),
                'loose': extract_price(document, '#used_price > span.price.js-price')
            }
        }
    except requests.RequestException as e:
        raise ValueError(f"HTTP request failed: {e}")

def retrieve_games(db_path: str, max_prices: Optional[int] = None) -> List[str]:
    base_query = """
        SELECT pricecharting_id
        FROM latest_prices
        WHERE retrieve_time < datetime('now', '-7 days')
        OR retrieve_time IS NULL
        ORDER BY name ASC
    """
    
    try:
        with sqlite3.connect(db_path) as con:
            if max_prices:
                cursor = con.execute(base_query + " LIMIT ?", (max_prices,))
            else:
                cursor = con.execute(base_query)
            return [row[0] for row in cursor]
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []

def process_batch(games: List[str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    successful, failed = [], []
    for game_id in games:
        try:
            successful.append(get_game_prices(game_id))
        except ValueError as err:
            failed.append({'game': game_id, 'message': str(err)})
            print(f"Error on game {game_id}: {err}")
    return successful, failed

def insert_price_records(games: List[Dict[str, Any]], db_path: str) -> None:
    records = [
        (record['game'], record['time'], record['prices'][condition], condition)
        for record in games
        for condition, price in record['prices'].items()
        if price is not None
    ]

    with sqlite3.connect(db_path) as con:
        con.executemany("""
            INSERT INTO pricecharting_prices 
            (pricecharting_id, retrieve_time, price, condition)
            VALUES (?,?,?,?)
        """, records) 