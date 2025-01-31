import pytest
from unittest.mock import Mock, patch, MagicMock
from bs4 import BeautifulSoup
import sqlite3
from lib.id_retrieval import (
    extract_id, extract_upcs, extract_asin,
    clean_game_name, clean_system_name,
    get_game_id, retrieve_games, insert_game_ids
)

# Sample HTML content for testing
SAMPLE_HTML = """
<div id="game-page">
    <div id="product_name" title="Super Mario 64"></div>
    <div id="full_details">
        <table id="attribute">
            <tr><td class="details">123456789012</td></tr>
            <tr><td class="details">B0ABCDE123</td></tr>
        </table>
    </div>
</div>
"""

SAMPLE_HTML_MULTIPLE_UPCS = """
<div id="game-page">
    <div id="product_name" title="Super Mario 64"></div>
    <div id="full_details">
        <table id="attribute">
            <tr><td class="details">123456789012,987654321098</td></tr>
        </table>
    </div>
</div>
"""

@pytest.fixture
def sample_soup():
    return BeautifulSoup(SAMPLE_HTML, 'html.parser')

@pytest.fixture
def sample_soup_multiple_upcs():
    return BeautifulSoup(SAMPLE_HTML_MULTIPLE_UPCS, 'html.parser')

def test_extract_id(sample_soup):
    assert extract_id(sample_soup) == "Super Mario 64"

def test_extract_id_no_element():
    soup = BeautifulSoup("<div></div>", 'html.parser')
    assert extract_id(soup) is None

def test_extract_upcs_single(sample_soup):
    assert extract_upcs(sample_soup) == ["123456789012"]

def test_extract_upcs_multiple(sample_soup_multiple_upcs):
    assert extract_upcs(sample_soup_multiple_upcs) == ["123456789012", "987654321098"]

def test_extract_upcs_no_match():
    soup = BeautifulSoup("<div></div>", 'html.parser')
    assert extract_upcs(soup) is None

def test_extract_asin(sample_soup):
    assert extract_asin(sample_soup) == "B0ABCDE123"

def test_extract_asin_no_match():
    soup = BeautifulSoup("<div></div>", 'html.parser')
    assert extract_asin(soup) is None

def test_clean_game_name():
    test_cases = [
        ("Super Mario 64", "super-mario-64"),
        ("The Legend of Zelda: Ocarina of Time", "the-legend-of-zelda-ocarina-of-time"),
        ("Crash Bandicoot [Greatest Hits]", "crash-bandicoot-greatest-hits"),
        ("Tony Hawk's Pro Skater", "tony-hawk%27s-pro-skater"),
        ("F-Zero X", "f-zero-x"),
    ]
    for input_name, expected in test_cases:
        assert clean_game_name(input_name) == expected

def test_clean_system_name():
    test_cases = [
        ("PlayStation", "playstation"),
        ("New Nintendo 3DS", "nintendo-3ds"),
        ("Nintendo 64", "nintendo-64"),
    ]
    for input_name, expected in test_cases:
        assert clean_system_name(input_name) == expected

@patch('lib.id_retrieval.requests.get')
def test_get_game_id(mock_get):
    # Mock the response
    mock_response = Mock()
    mock_response.content = SAMPLE_HTML
    mock_get.return_value = mock_response

    result = get_game_id(1, "Super Mario 64", "Nintendo 64")
    
    assert result == {
        'id': 1,
        'name': "Super Mario 64",
        'console': "Nintendo 64",
        'pricecharting_id': "Super Mario 64",
        'upcs': ["123456789012"],
        'asin': "B0ABCDE123",
        'url': "https://www.pricecharting.com/game/nintendo-64/super-mario-64"
    }

@patch('lib.id_retrieval.requests.get')
def test_get_game_id_error(mock_get):
    # Mock the response with HTML that won't have a product name
    mock_response = Mock()
    mock_response.content = "<div></div>"
    mock_get.return_value = mock_response

    with pytest.raises(ValueError):
        get_game_id(1, "Invalid Game", "Nintendo 64")

@patch('sqlite3.connect')
def test_retrieve_games(mock_connect):
    # Mock cursor and connection
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        (1, "Super Mario 64", "Nintendo 64"),
        (2, "Sonic the Hedgehog", "Genesis")
    ]
    mock_connection = MagicMock()
    mock_connection.execute.return_value = mock_cursor
    mock_connect.return_value.__enter__.return_value = mock_connection

    results = retrieve_games("test.db")
    assert len(results) == 2
    assert results[0] == (1, "Super Mario 64", "Nintendo 64")
    assert results[1] == (2, "Sonic the Hedgehog", "Genesis")

@patch('sqlite3.connect')
def test_insert_game_ids(mock_connect):
    # Test data
    games = [
        {
            'id': 1,
            'name': "Super Mario 64",
            'console': "Nintendo 64",
            'pricecharting_id': "Super Mario 64",
            'url': "https://www.pricecharting.com/game/nintendo-64/super-mario-64"
        }
    ]

    # Mock connection
    mock_connection = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_connection

    result = insert_game_ids(games, "test.db")
    assert result == 1  # One record inserted

    # Verify executemany was called with correct parameters
    mock_connection.executemany.assert_called_once()
