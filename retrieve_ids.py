import sqlite3
import requests
from bs4 import BeautifulSoup
import json
import sys
import re

dbname=sys.argv[1]

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

def get_game_id(internal_id, game_name, system_name):
    cleaned_game = clean_game_name(game_name)
    cleaned_system = clean_system_name(system_name)

    print(f"{game_name} on {system_name}...", file=sys.stderr)

    url = f"https://www.pricecharting.com/game/{cleaned_system}/{cleaned_game}"
    response = requests.get(url)
    document = BeautifulSoup(response.content, 'html.parser')

    id = extract_id(document)
    if id is None:
        raise ValueError(f"Couldn't infer game URL: {url}")

    return {
        'id': internal_id,
        'name': game_name,
        'console': system_name,
        'pricecharting_id': id,
        'upcs': extract_upcs(document),
        'asin': extract_asin(document),
        'url': url
    }

def clean_game_name(original):
    return original.lower().strip().replace(':', '').replace('.', '').replace("'", '%27').replace(' ', '-').replace('--', '-').replace('--', '-').replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('/', '').replace('#', '').strip()

def clean_system_name(original):
    return original.lower().replace('new', '').strip().replace(' ', '-')

def get_games():
    statement = """
    SELECT id, name, console
    FROM pricecharting_games
    WHERE pricecharting_id IS NULL
    ORDER BY name ASC
    """
    
    con = sqlite3.connect(dbname)
    with con:
        cursor = con.execute(statement, ())
        res = cursor.fetchall()
    con.close()
    return res

def insert_game_ids(dbname, games):
    """
    Insert a batch of game IDs into the database.
    
    Args:
        dbname (str): Path to the SQLite database
        games (list): List of game dictionaries with pricecharting_id, url, id, name, and console keys
    
    Returns:
        int: Number of records inserted
    """
    statement = """
    REPLACE INTO pricecharting_games 
    (pricecharting_id, url, id, name, console) 
    VALUES (?,?,?,?,?)
    """
    
    updates = [
        (record['pricecharting_id'], record['url'], record['id'], 
         record['name'], record['console']) for record in games
    ]

    try:
        with sqlite3.connect(dbname) as con:
            con.executemany(statement, updates)
        return len(games)
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        raise

def main():
    # Find all of the games with missing pricecharting identifiers
    games = get_games()
    if (len(games) <= 0):
        print("No unidentified games found.", file=sys.stderr)
        exit()

    print(f"Retrieving identifiers for {len(games)} games:", file=sys.stderr)

    failed = []
    retrieved = []
    for id, name, console in games:
        try:
            data = get_game_id(id, name, console)
            retrieved.append(data)
        except ValueError as err:
            msg = f"Could not retrieve info: {err}"
            failed.append({'game': id, 'name': name, 'message': msg})
    
    # Save retrieved records to database
    if retrieved:
        try:
            records_inserted = insert_game_ids(dbname, retrieved)
            print(f"Saved {records_inserted} records to database", file=sys.stderr)
        except sqlite3.Error as e:
            print(f"Failed to save records to database: {e}", file=sys.stderr)

    if failed:
        print("Failures:", file=sys.stderr)
        print(json.dumps(failed, indent=2), file=sys.stderr)

if __name__ == '__main__':
    main()
