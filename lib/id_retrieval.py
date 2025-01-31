import sqlite3
import requests
from bs4 import BeautifulSoup
import re
from typing import List, Dict, Any, Optional, Tuple, Union

upc_regex = re.compile("^[0-9]{12}$")
asin_regex = re.compile("^B0[A-Z0-9]{8}$")

def extract_id(document: BeautifulSoup) -> Optional[str]:
    element = document.select_one('#product_name')
    if element:
        text = element.get('title').strip()
        return text.replace(',', '')
    return None

def extract_upcs(document: BeautifulSoup) -> Optional[List[str]]:
    elements = document.select('#game-page #full_details #attribute td.details')
    for element in elements:
        text = element.text.strip()
        if upc_regex.match(text[:12]):
            if len(text) > 12 and text[12] == ',':
                return text.split(',')
            elif len(text) == 12:
                return [text]
    return None

def extract_asin(document: BeautifulSoup) -> Optional[str]:
    elements = document.select('#game-page #full_details #attribute td.details')
    for element in elements:
        text = element.text.strip()
        if asin_regex.match(text):
            return text
    return None

def clean_game_name(original: str) -> str:
    return original.lower().strip().replace(':', '').replace('.', '').replace("'", '%27').replace(' ', '-').replace('--', '-').replace('--', '-').replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('/', '').replace('#', '').strip()

def clean_system_name(original: str) -> str:
    return original.lower().replace('new', '').strip().replace(' ', '-')

def get_game_id(internal_id: int, game_name: str, system_name: str) -> Dict[str, Any]:
    cleaned_game = clean_game_name(game_name)
    cleaned_system = clean_system_name(system_name)

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

def retrieve_games(connection: Union[str, sqlite3.Connection]) -> List[Tuple[int, str, str]]:
    statement = """
    SELECT id, name, console
    FROM pricecharting_games
    WHERE pricecharting_id IS NULL
    ORDER BY name ASC
    """
    
    if isinstance(connection, str):
        with sqlite3.connect(connection) as conn:
            cursor = conn.execute(statement)
            return cursor.fetchall()
    else:
        cursor = connection.execute(statement)
        return cursor.fetchall()

def insert_game_ids(games: List[Dict[str, Any]], connection: Union[str, sqlite3.Connection]) -> int:
    statement = """
    REPLACE INTO pricecharting_games 
    (pricecharting_id, url, id, name, console) 
    VALUES (?,?,?,?,?)
    """
    
    updates = [
        (record['pricecharting_id'], record['url'], record['id'], 
         record['name'], record['console']) for record in games
    ]

    if isinstance(connection, str):
        with sqlite3.connect(connection) as conn:
            conn.executemany(statement, updates)
            conn.commit()
    else:
        connection.executemany(statement, updates)
        
    return len(games)