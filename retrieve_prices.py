import requests
import datetime
from bs4 import BeautifulSoup
import json
import sys

# This must contain a list of pricecharting identifiers (probably extracted via retrieve-ids.py)
filename=sys.argv[1]

# List of 
with open(filename) as file:
    games = [line.rstrip() for line in file]

# Function to extract price from HTML using CSS selector
def extract_price(document, selector):
    price_element = document.select_one(selector)
    if price_element:
        price_text = price_element.text.strip()
        if price_text.startswith('$'):
            price_text = price_text[1:]
        return float(price_text.replace(',', ''))
    return None

# Function to retrieve pricing data for a game
def get_game_prices(id):
    url = f"https://www.pricecharting.com/game/{id}"
    response = requests.get(url)
    print(f"Got response from {url}")
    document = BeautifulSoup(response.content, 'html.parser')

    prices = {
        'complete': extract_price(document, '#complete_price > span.price.js-price'),
        'new': extract_price(document, '#new_price > span.price.js-price'),
        'loose': extract_price(document, '#used_price > span.price.js-price')
    }

    return {
        'time': datetime.datetime.now().isoformat(),
        'game': id,
        'prices': prices,
        'url': url
    }

# Main function
def main():
    failures = []
    price_data = []
    for game_id in games:
        try:
            prices = get_game_prices(game_id)
            price_data.append(prices)
        except ValueError as err:
            failures.append(game_id)
            print(f"Could not retrieve pricing information for {game_id}", err)
    print(json.dumps(price_data, indent=2))
    print(json.dumps(failures, indent=2))

# Run the main function
if __name__ == '__main__':
    main()
