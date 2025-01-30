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

        # Use UTC time explicitly
        current_time = datetime.datetime.utcnow().isoformat()

        return {
            'time': current_time,
            'game': game_id,
            'prices': {
                'complete': extract_price(document, '#complete_price > span.price.js-price'),
                'new': extract_price(document, '#new_price > span.price.js-price'),
                'loose': extract_price(document, '#used_price > span.price.js-price')
            }
        }
    except requests.RequestException as e:
        print(f"\nError retrieving prices for game {game_id}: {e}")
        return None

def retrieve_games(db_path: str, max_prices: Optional[int] = None) -> List[str]:
    base_query = """
        SELECT DISTINCT pricecharting_id
        FROM eligible_price_updates
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

def insert_price_records(games: List[Dict[str, Any]], db_path: str) -> None:
    records = []
    for record in games:
        if record is None:
            continue
            
        has_prices = False
        for condition, price in record['prices'].items():
            records.append((record['game'], record['time'], price, condition))
            if price is not None:
                has_prices = True
                
        # If no prices were found, insert a single null record to mark the attempt
        if not has_prices:
            records.append((record['game'], record['time'], None, 'new'))
    
    with sqlite3.connect(db_path) as con:
        con.execute("PRAGMA foreign_keys = ON")
        con.executemany("""
            INSERT INTO pricecharting_prices 
            (pricecharting_id, retrieve_time, price, condition)
            VALUES (?,?,?,?)
        """, records)

        # Verify the insertions with raw timestamp data
        cursor = con.cursor()
        cursor.execute("""
            SELECT pricecharting_id, 
                   retrieve_time,
                   typeof(retrieve_time),
                   price, 
                   condition,
                   datetime('now', '-7 days')
            FROM pricecharting_prices
            ORDER BY retrieve_time DESC
            LIMIT 5
        """)
        
        print("\nDebug - Most recent records in database:")
        for row in cursor.fetchall():
            print(f"ID: {row[0]}")
            print(f"  Time: {row[1]} (type: {row[2]})")
            print(f"  Price: {row[3]}")
            print(f"  Condition: {row[4]}")
            print(f"  7 days ago: {row[5]}")
            print()

        # Check if any records are being found by the eligibility check
        cursor.execute("""
            SELECT COUNT(*) 
            FROM pricecharting_prices 
            WHERE retrieve_time >= datetime('now', '-7 days')
        """)
        recent_count = cursor.fetchone()[0]
        print(f"Records found in last 7 days: {recent_count}") 