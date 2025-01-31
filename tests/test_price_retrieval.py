import pytest
from unittest.mock import Mock, patch
import datetime
import sqlite3
from bs4 import BeautifulSoup
from lib.price_retrieval import get_game_prices, retrieve_games, insert_price_records, extract_price
from collection import GameLibrary
import requests

@pytest.fixture
def db_connection():
    """Create an in-memory database for testing."""
    conn = sqlite3.connect(':memory:')
    with open('schema/collection.sql', 'r') as f:
        conn.executescript(f.read())
    return conn

def test_null_price_handling(db_connection):
    """Test handling of null prices in price retrieval."""
    # Insert a test game record
    db_connection.execute("""
        INSERT INTO pricecharting_games (pricecharting_id, name, console) 
        VALUES (?, ?, ?)
    """, (1001, 'Test Game', 'Switch'))
    
    # Mock a response with no prices
    mock_response = Mock()
    mock_response.content = """
        <html>
            <div id="complete_price"><span class="price js-price">-</span></div>
            <div id="new_price"><span class="price js-price">-</span></div>
            <div id="used_price"><span class="price js-price">-</span></div>
        </html>
    """
    
    with patch('requests.get') as mock_get:
        mock_get.return_value = mock_response
        # Get prices for a game
        game_id = "test123"
        result = get_game_prices(game_id)
        
        # Verify all prices are None
        assert all(price is None for price in result['prices'].values())
        
        # Insert the record directly using the connection
        records = []
        for condition, price in result['prices'].items():
            records.append((game_id, result['time'], price, condition))
        
        db_connection.executemany("""
            INSERT INTO pricecharting_prices
            (pricecharting_id, retrieve_time, price, condition)
            VALUES (?,?,?,?)
        """, records)
        
        # Verify records were inserted with null prices
        cursor = db_connection.execute("""
            SELECT pricecharting_id, price, condition
            FROM pricecharting_prices
            WHERE pricecharting_id = ?
            ORDER BY condition
        """, (game_id,))
        records = cursor.fetchall()
        
        # Should have records for all conditions with null prices
        assert len(records) == 3  # complete, loose, new
        conditions = [r[2] for r in records]
        assert sorted(conditions) == ['complete', 'loose', 'new']
        assert all(r[1] is None for r in records)  # all prices should be null 

def test_retrieve_games(db_connection):
    """Test retrieving games that need price updates."""
    # Insert test data
    db_connection.executemany("""
        INSERT INTO physical_games (name, console) VALUES (?, ?)
    """, [
        ("Game 1", "Switch"),
        ("Game 2", "PS5"),
        ("Game 3", "Xbox"),
    ])
    
    db_connection.executemany("""
        INSERT INTO pricecharting_games (pricecharting_id, name, console) VALUES (?, ?, ?)
    """, [
        (1001, "Game 1", "Switch"),
        (1002, "Game 2", "PS5"),
        (1003, "Game 3", "Xbox"),
    ])
    
    # Link games to pricecharting IDs
    db_connection.executemany("""
        INSERT INTO physical_games_pricecharting_games (physical_game, pricecharting_game)
        VALUES (?, ?)
    """, [(1, 1), (2, 2), (3, 3)])
    
    # Add a recent price for Game 2 (within 7 days)
    db_connection.execute("""
        INSERT INTO pricecharting_prices (pricecharting_id, retrieve_time, price, condition)
        VALUES (?, datetime('now', '-1 day'), 59.99, 'new')
    """, (1002,))
    
    # Add an old price for Game 3 (over 7 days old)
    db_connection.execute("""
        INSERT INTO pricecharting_prices (pricecharting_id, retrieve_time, price, condition)
        VALUES (?, datetime('now', '-10 days'), 49.99, 'new')
    """, (1003,))
    
    db_connection.commit()
    
    # Test retrieving eligible games directly using the connection
    cursor = db_connection.execute("""
        SELECT DISTINCT pricecharting_id
        FROM eligible_price_updates
        ORDER BY name ASC
    """)
    games = [row[0] for row in cursor.fetchall()]
    
    # Should get Game 1 (never updated) and Game 3 (old update)
    assert len(games) == 2
    assert 1001 in games  # Never had a price update
    assert 1003 in games  # Has an old price update
    assert 1002 not in games  # Has a recent price update
    
    # Test with max_prices limit by using LIMIT in SQL
    cursor = db_connection.execute("""
        SELECT DISTINCT pricecharting_id
        FROM eligible_price_updates
        ORDER BY name ASC
        LIMIT 1
    """)
    limited_games = [row[0] for row in cursor.fetchall()]
    assert len(limited_games) == 1
    assert limited_games[0] in [1001, 1003]  # Should get one of the eligible games

def test_retrieve_games_with_numeric_max_prices(db_connection):
    """Test retrieving games from the database."""
    # Insert physical games
    db_connection.executemany("""
        INSERT INTO physical_games (id, name, console) 
        VALUES (?, ?, ?)
    """, [
        (1, 'Game A', 'Switch'),
        (2, 'Game B', 'PS5'),
        (3, 'Game C', 'Xbox'),
        (4, 'Game D', 'PS4'),
        (5, 'Game E', 'Switch')
    ])
    
    # Insert pricecharting games
    db_connection.executemany("""
        INSERT INTO pricecharting_games (id, pricecharting_id, name, console) 
        VALUES (?, ?, ?, ?)
    """, [
        (1, 1001, 'Game A', 'Switch'),
        (2, 1002, 'Game B', 'PS5'),
        (3, 1003, 'Game C', 'Xbox'),
        (4, 1004, 'Game D', 'PS4'),
        (5, 1005, 'Game E', 'Switch')
    ])
    
    # Link physical games to pricecharting games
    db_connection.executemany("""
        INSERT INTO physical_games_pricecharting_games (physical_game, pricecharting_game)
        VALUES (?, ?)
    """, [
        (1, 1),  # Game A
        (2, 2),  # Game B
        (3, 3),  # Game C
        (4, 4),  # Game D
        (5, 5)   # Game E
    ])
    
    # Insert some test prices
    current_time = datetime.datetime.utcnow().isoformat()
    old_time = (datetime.datetime.utcnow() - datetime.timedelta(days=8)).isoformat()
    
    db_connection.executemany("""
        INSERT INTO pricecharting_prices 
        (pricecharting_id, retrieve_time, price, condition)
        VALUES (?, ?, ?, ?)
    """, [
        # Game A - needs update (old price)
        (1001, old_time, 49.99, 'new'),
        # Game B - needs update (no recent price)
        (1002, old_time, 39.99, 'new'),
        # Game C - needs update (old price)
        (1003, old_time, 29.99, 'new'),
        # Game D - doesn't need update (recent price)
        (1004, current_time, 39.99, 'new'),
        # Game E - doesn't need update (recent price)
        (1005, current_time, 59.99, 'new')
    ])
    
    # Add games to purchased_games to make them eligible for price updates
    db_connection.executemany("""
        INSERT INTO purchased_games (physical_game, acquisition_date, source, price, condition)
        VALUES (?, ?, ?, ?, ?)
    """, [
        (1, '2024-01-01', 'Store', 49.99, 'new'),  # Game A
        (2, '2024-01-01', 'Store', 39.99, 'new'),  # Game B
        (3, '2024-01-01', 'Store', 29.99, 'new'),  # Game C
        (4, '2024-01-01', 'Store', 39.99, 'new'),  # Game D
        (5, '2024-01-01', 'Store', 59.99, 'new')   # Game E
    ])
    
    # Commit changes to ensure views are updated
    db_connection.commit()
    
    # Test retrieving all eligible games (no limit)
    games = retrieve_games(db_connection)
    assert len(games) == 3  # Should get games A, B, and C
    assert set(games) == {1001, 1002, 1003}  # These games need updates
    
    # Test retrieving with limit=1
    limited_games = retrieve_games(db_connection, max_prices=1)
    assert len(limited_games) == 1
    assert limited_games[0] in [1001, 1002, 1003]  # Should get one of the eligible games
    
    # Test retrieving with limit=2
    limited_games = retrieve_games(db_connection, max_prices=2)
    assert len(limited_games) == 2
    assert set(limited_games).issubset({1001, 1002, 1003})  # Should get two of the eligible games
    
    # Test retrieving with limit larger than available games
    limited_games = retrieve_games(db_connection, max_prices=10)
    assert len(limited_games) == 3  # Should still only get the three eligible games
    assert set(limited_games) == {1001, 1002, 1003}
    
    # Test retrieving with limit=0
    limited_games = retrieve_games(db_connection, max_prices=0)
    assert len(limited_games) == 0  # Should get no games

def test_insert_price_records(db_connection, tmp_path):
    """Test inserting price records into the database."""
    # Create a temporary database file
    db_path = tmp_path / "test.db"
    
    # Copy the schema and data from the in-memory database to the file
    db_connection.execute("VACUUM INTO ?", (str(db_path),))
    db_connection.close()
    
    # Create a new connection to the file
    db_connection = sqlite3.connect(db_path)
    
    # Insert a game first
    db_connection.execute("""
        INSERT INTO pricecharting_games (pricecharting_id, name, console) 
        VALUES (?, ?, ?)
    """, (1001, 'Test Game', 'Switch'))
    db_connection.commit()
    
    # Test case 1: Game with some prices
    game_with_prices = {
        'game': 1001,
        'time': '2025-01-30T21:35:59',
        'prices': {
            'complete': 49.99,
            'loose': None,
            'new': 59.99
        }
    }
    
    # Test case 2: Game with all null prices
    game_with_null_prices = {
        'game': 1001,
        'time': '2025-01-30T21:36:00',
        'prices': {
            'complete': None,
            'loose': None,
            'new': None
        }
    }
    
    # Test case 3: None record (should be skipped)
    none_record = None
    
    # Insert all test cases
    records = [game_with_prices, game_with_null_prices, none_record]
    
    # Use the actual insert_price_records function
    insert_price_records(records, str(db_path))
    
    # Verify records for game with prices
    cursor = db_connection.execute("""
        SELECT condition, price
        FROM pricecharting_prices
        WHERE pricecharting_id = ? AND retrieve_time = ?
        ORDER BY condition
    """, (1001, '2025-01-30T21:35:59'))
    records = cursor.fetchall()
    
    assert len(records) == 3
    assert records[0] == ('complete', 49.99)  # complete price
    assert records[1] == ('loose', None)      # null loose price
    assert records[2] == ('new', 59.99)       # new price
    
    # Verify records for game with all null prices
    cursor = db_connection.execute("""
        SELECT condition, price
        FROM pricecharting_prices
        WHERE pricecharting_id = ? AND retrieve_time = ?
        ORDER BY condition
    """, (1001, '2025-01-30T21:36:00'))
    records = cursor.fetchall()
    
    # Should have one record per condition (complete, loose, new) plus an extra null record
    assert len(records) == 4
    assert all(record[1] is None for record in records)  # All prices should be null
    
    # Verify conditions - should have one of each plus an extra 'new'
    conditions = [record[0] for record in records]
    assert conditions.count('complete') == 1
    assert conditions.count('loose') == 1
    assert conditions.count('new') == 2  # One from the regular insert, one from marking the attempt
    
    db_connection.close()

def test_get_game_prices_error_handling():
    """Test error handling in get_game_prices function."""
    # Test case 1: Connection error
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.ConnectionError("Failed to connect")
        result = get_game_prices("test123")
        assert result is None  # Should return None on error
        
    # Test case 2: HTTP error
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response
        result = get_game_prices("test123")
        assert result is None  # Should return None on error
        
    # Test case 3: Timeout error
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.Timeout("Request timed out")
        result = get_game_prices("test123")
        assert result is None  # Should return None on error
        
    # Test case 4: TooManyRedirects error
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.TooManyRedirects("Too many redirects")
        result = get_game_prices("test123")
        assert result is None  # Should return None on error

def test_retrieve_games_error_handling(db_connection):
    """Test error handling in retrieve_games function."""
    # Drop the view to simulate a missing table error
    db_connection.execute("DROP VIEW IF EXISTS eligible_price_updates")
    
    # Test with missing view
    games = retrieve_games(db_connection)
    assert len(games) == 0  # Should return empty list on error

def test_extract_price():
    """Test the extract_price function."""
    from lib.price_retrieval import extract_price
    
    # Test case 1: Price with $ symbol and no commas
    html = """
    <html>
        <div class="price">$49.99</div>
    </html>
    """
    document = BeautifulSoup(html, 'html.parser')
    assert extract_price(document, '.price') == 49.99
    
    # Test case 2: Price with $ symbol and commas
    html = """
    <html>
        <div class="price">$1,234.56</div>
    </html>
    """
    document = BeautifulSoup(html, 'html.parser')
    assert extract_price(document, '.price') == 1234.56
    
    # Test case 3: Price without $ symbol
    html = """
    <html>
        <div class="price">99.99</div>
    </html>
    """
    document = BeautifulSoup(html, 'html.parser')
    assert extract_price(document, '.price') == 99.99
    
    # Test case 4: Invalid price (dash)
    html = """
    <html>
        <div class="price">-</div>
    </html>
    """
    document = BeautifulSoup(html, 'html.parser')
    assert extract_price(document, '.price') is None
    
    # Test case 5: Element not found
    html = """
    <html>
        <div class="other">$49.99</div>
    </html>
    """
    document = BeautifulSoup(html, 'html.parser')
    assert extract_price(document, '.price') is None
    
    # Test case 6: Price with whitespace
    html = """
    <html>
        <div class="price">  $  49.99  </div>
    </html>
    """
    document = BeautifulSoup(html, 'html.parser')
    assert extract_price(document, '.price') == 49.99