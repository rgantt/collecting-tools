import sqlite3
import requests
import datetime
from bs4 import BeautifulSoup
import json
import sys

dbname=sys.argv[1]

statement = """
SELECT pricecharting_id
FROM latest_prices
WHERE retrieve_time < datetime('now', '-3 days')
ORDER BY name ASC
"""

def extract_price(document, selector):
    price_element = document.select_one(selector)
    if price_element:
        price_text = price_element.text.strip()
        if price_text.startswith('$'):
            price_text = price_text[1:]
        price_text = price_text.replace(',', '')
        if price_text == '-':
            return None
        else:
            return float(price_text)
    return None

def get_game_prices(id):
    url = f"https://www.pricecharting.com/game/{id}"
    response = requests.get(url)
    document = BeautifulSoup(response.content, 'html.parser')

    prices = {
        'complete': extract_price(document, '#complete_price > span.price.js-price'),
        'new': extract_price(document, '#new_price > span.price.js-price'),
        'loose': extract_price(document, '#used_price > span.price.js-price')
    }

    return {
        'time': datetime.datetime.now().isoformat(),
        'game': id,
        'prices': prices
    }


def retrieve_games():
    con = sqlite3.connect(dbname)
    with con:
        cursor = con.execute(statement, ())
        res = cursor.fetchall()
    con.close()
    return [x[0] for x in res]

def insert_price_records(dbname, games):
    """
    Insert a batch of price records into the database.
    
    Args:
        dbname (str): Path to the SQLite database
        games (list): List of game dictionaries with 'game', 'time', and 'prices' keys
    
    Returns:
        int: Number of records inserted
    """
    statement = """
    INSERT INTO pricecharting_prices 
    (pricecharting_id, retrieve_time, price, condition)
    VALUES 
    (?,?,?,?)
    """
    
    records = []
    for record in games:
        prices = record['prices']
        records.append((record['game'], record['time'], prices['new'], 'new'))
        records.append((record['game'], record['time'], prices['loose'], 'loose'))
        records.append((record['game'], record['time'], prices['complete'], 'complete'))

    try:
        with sqlite3.connect(dbname) as con:
            con.executemany(statement, records)
        return len(games)
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        raise

def main():
    failed = []
    price_data = []

    games = retrieve_games()
    if not games:
        print("No games found.", file=sys.stderr)
        sys.exit(1)

    print(f"Retrieving prices for {len(games)} games...", file=sys.stderr)
    for count, game_id in enumerate(games, 1):
        try:
            prices = get_game_prices(game_id)
            price_data.append(prices)
            if count % 50 == 0:
                print(f"Progress: {count}/{len(games)} prices retrieved", file=sys.stderr)
                # Optionally commit to database in batches
                try:
                    insert_price_records(dbname, price_data)
                    price_data = []  # Clear after successful insert
                except sqlite3.Error as e:
                    print(f"Failed to save batch to database: {e}", file=sys.stderr)
        except ValueError as err:
            msg = f"Could not retrieve pricing info: {err}"
            failed.append({'game': game_id, 'message': msg})
            print(f"Error on game {game_id}: {err}", file=sys.stderr)
    
    # Insert any remaining records
    if price_data:
        try:
            insert_price_records(dbname, price_data)
        except sqlite3.Error as e:
            print(f"Failed to save final batch to database: {e}", file=sys.stderr)
    
    print(f"Completed: {len(price_data)}/{len(games)} prices retrieved", file=sys.stderr)
    
    if failed:
        print(f"\nFailures ({len(failed)}):", file=sys.stderr)
        print(json.dumps(failed, indent=2), file=sys.stderr)

if __name__ == '__main__':
    main()
