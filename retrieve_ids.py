import requests
from bs4 import BeautifulSoup
import json
import sys
import re

# This must contain a list of "PriceCharting-compatible" names (which are aggravatingly different than title names)
filename=sys.argv[1]

# List of video games
with open(filename) as file:
    games = [line.rstrip() for line in file]

def extract_id(document):
    element = document.select_one('#product_name')
    if element:
        text = element.get('title').strip()
        return text.replace(',', '')
    return None

upc_regex = re.compile("^[0-9]{12}$")
asin_regex = re.compile("^B0[A-Z0-9]{8}$")

def extract_upcs(document):
    elements = document.select('#game-page #full_details #attribute td.details')
    for element in elements:
        text = element.text.strip()
        if upc_regex.match(text[:12]):
            if len(text) > 12 and text[12] == ',':
                return text.split(',')
            elif len(text) == 12:
                return [text]
    return None

def extract_asin(document):
    elements = document.select('#game-page #full_details #attribute td.details')
    for element in elements:
        text = element.text.strip()
        if asin_regex.match(text):
            return text
    return None

# Function to retrieve pricing data for a game
def get_game_id(game_name, system_name):
    cleaned_game = clean_game_name(game_name)
    cleaned_system = clean_system_name(system_name)
    url = f"https://www.pricecharting.com/game/{cleaned_system}/{cleaned_game}"
    response = requests.get(url)
    document = BeautifulSoup(response.content, 'html.parser')

    id = extract_id(document)

    if id is None:
        raise ValueError(f"Couldn't infer game URL: {url}")

    return {
        'name': game_name,
        'pricecharting_id': id,
        'upcs': extract_upcs(document),
        'asin': extract_asin(document),
        'url': url
    }

def clean_game_name(original):
    return original.lower().strip().replace(':', '').replace('.', '').replace("'", '%27').replace(' ', '-').replace('--', '-').replace('--', '-').replace('(', '').replace(')', '').replace('[', '').replace(']', '').strip()

def clean_system_name(original):
    return original.lower().replace('new', '').strip().replace(' ', '-')

# Main function
def main():
    failed = []
    retrieved = []
    for game in games:
        game_name, system_name = game.split(',')
        try:
            data = get_game_id(game_name, clean_system_name(system_name))
            retrieved.append(data)
        except ValueError as err:
            msg = f"Could not retrieve info: {err}"
            failed.append({'game': game, 'message': msg})
    print(json.dumps(retrieved, indent=2))
    print(json.dumps(failed, indent=2))

# Run the main function
if __name__ == '__main__':
    main()
