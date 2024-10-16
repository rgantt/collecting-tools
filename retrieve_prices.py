import sqlite3
import requests
import datetime
from bs4 import BeautifulSoup
import json
import sys

dbname=sys.argv[1]

statement="""
SELECT pricecharting_id
FROM pricecharting_games
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


def main():
    failed = []
    price_data = []
    i = 0

    games = retrieve_games()
    if (len(games) <= 0):
        print("No games found.", file=sys.stderr)
        exit()

    print(f"Retrieving prices for {len(games)} games:", file=sys.stderr)
    for game_id in games:
        try:
            prices = get_game_prices(game_id)
            price_data.append(prices)
            i += 1
            if (i % 50 == 0):
                print(f"Retrieved {i}/{len(games)} prices...", file=sys.stderr)
        except ValueError as err:
            msg = f"Could not retrieve pricing info: {err}"
            failed.append({'game': game_id, 'message': msg})
    print(json.dumps(price_data, indent=2))

    if (len(failed) > 0):
        print("Failures:", file=sys.stderr)
        print(json.dumps(failed, indent=2), file=sys.stderr)

if __name__ == '__main__':
    main()
