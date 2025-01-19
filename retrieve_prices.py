import sqlite3
import requests
import datetime
from bs4 import BeautifulSoup
import json
import sys
import argparse

def extract_price(document, selector):
    if price_element := document.select_one(selector):
        price_text = price_element.text.strip()
        if price_text.startswith('$'):
            price_text = price_text[1:]
        price_text = price_text.replace(',', '')
        return None if price_text == '-' else float(price_text)
    return None

def get_game_prices(game_id):
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

def retrieve_games(db_path, max_prices):
    base_query = """
        SELECT pricecharting_id
        FROM latest_prices
        WHERE retrieve_time < datetime('now', '-1 minutes')
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
        sys.exit(1)

def insert_price_records(games, db_path):
    records = [
        (record['game'], record['time'], record['prices'][condition], condition)
        for record in games
        for condition, price in record['prices'].items()
    ]

    try:
        with sqlite3.connect(db_path) as con:
            con.executemany("""
                INSERT INTO pricecharting_prices 
                (pricecharting_id, retrieve_time, price, condition)
                VALUES (?,?,?,?)
            """, records)
        return len(games)
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        raise

def process_batch(games):
    successful, failed = [], []
    for game_id in games:
        try:
            successful.append(get_game_prices(game_id))
        except ValueError as err:
            failed.append({'game': game_id, 'message': f"Could not retrieve pricing info: {err}"})
    return successful, failed

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('db_path', help='Path to SQLite database')
    parser.add_argument('--batch-size', type=int, default=50, help='Maximum number of games to process in each batch')
    parser.add_argument('--max-prices', type=int, help='Maximum number of prices to retrieve')
    args = parser.parse_args()

    batch_size = args.batch_size

    games = retrieve_games(args.db_path, args.max_prices)
    if not games:
        print("No games found with prices older than 3 days.")
        sys.exit(0)

    print(f"Retrieving prices for {len(games)} games...")
    all_failed = []
    processed = 0

    for i in range(0, len(games), batch_size):
        successful, failed = process_batch(games[i:i + batch_size])
        
        if successful:
            try:
                insert_price_records(successful, args.db_path)
                processed += len(successful)
                print(f"Progress: {processed}/{len(games)} prices retrieved")
            except sqlite3.Error as e:
                print(f"Failed to save batch to database: {e}")
        
        all_failed.extend(failed)
    
    print(f"Completed: {processed}/{len(games)} prices retrieved")
    
    if all_failed:
        print(f"\nFailures ({len(all_failed)}):")
        print(json.dumps(all_failed, indent=2))

if __name__ == '__main__':
    main()
