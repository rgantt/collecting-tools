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
    """Create a temporary in-memory database for testing."""
    con = sqlite3.connect(':memory:')
    con.execute("PRAGMA foreign_keys = ON")

    # Create tables
    con.executescript("""
        CREATE TABLE physical_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            console TEXT NOT NULL
        );

        CREATE TABLE pricecharting_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pricecharting_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            console TEXT NOT NULL,
            url TEXT
        );

        CREATE TABLE physical_games_pricecharting_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            physical_game INTEGER NOT NULL,
            pricecharting_game INTEGER NOT NULL,
            FOREIGN KEY (physical_game) REFERENCES physical_games (id),
            FOREIGN KEY (pricecharting_game) REFERENCES pricecharting_games (id)
        );

        CREATE TABLE pricecharting_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            retrieve_time TIMESTAMP,
            pricecharting_id INTEGER NOT NULL,
            condition TEXT,
            price DECIMAL,
            FOREIGN KEY (pricecharting_id) REFERENCES pricecharting_games (pricecharting_id)
        );

        CREATE TABLE purchased_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            physical_game INTEGER NOT NULL,
            acquisition_date DATE NOT NULL CHECK (acquisition_date IS strftime('%Y-%m-%d', acquisition_date)),
            source TEXT,
            price DECIMAL,
            condition TEXT,
            FOREIGN KEY (physical_game) REFERENCES physical_games (id)
        );

        CREATE TABLE wanted_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            physical_game INTEGER NOT NULL,
            FOREIGN KEY (physical_game) REFERENCES physical_games (id)
        );

        CREATE VIEW IF NOT EXISTS latest_prices AS
        WITH base_games AS (
            SELECT g.id, g.name, g.console
            FROM physical_games g
            LEFT JOIN purchased_games pg ON g.id = pg.physical_game
            UNION
            SELECT g.id, g.name, g.console
            FROM physical_games g
            JOIN wanted_games w ON g.id = w.physical_game
        )
        SELECT
            g.name,
            g.console,
            z.pricecharting_id,
            max(p.retrieve_time) as retrieve_time,
            p.price,
            p.condition
        FROM base_games g
        JOIN physical_games_pricecharting_games j
            ON g.id = j.physical_game
        JOIN pricecharting_games z
            ON j.pricecharting_game = z.id
        LEFT JOIN pricecharting_prices p
            ON z.pricecharting_id = p.pricecharting_id
        GROUP BY g.id, p.condition
        ORDER BY g.name ASC;

        CREATE VIEW IF NOT EXISTS eligible_price_updates AS
        WITH latest_updates AS (
            -- Get the most recent update time for each game, even if prices were null
            SELECT 
                pricecharting_id,
                MAX(retrieve_time) as last_update
            FROM pricecharting_prices
            GROUP BY pricecharting_id
        )
        SELECT DISTINCT
            g.name,
            g.console,
            z.pricecharting_id
        FROM physical_games g
        LEFT JOIN purchased_games pg
            ON g.id = pg.physical_game
        JOIN physical_games_pricecharting_games j
            ON g.id = j.physical_game
        JOIN pricecharting_games z
            ON j.pricecharting_game = z.id
        LEFT JOIN latest_updates lu
            ON z.pricecharting_id = lu.pricecharting_id
        WHERE lu.last_update IS NULL  -- Never attempted
           OR datetime(lu.last_update) < datetime('now', '-7 days')  -- Or old attempt (even if it was null)
        ORDER BY g.name ASC;
    """)

    yield con
    con.close()

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
        game_id = "1001"  # Use the correct game ID that exists in the database
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

    # Create the views
    db_connection.executescript("""
        CREATE VIEW IF NOT EXISTS latest_prices AS
        WITH base_games AS (
            SELECT g.id, g.name, g.console
            FROM physical_games g
            LEFT JOIN purchased_games pg ON g.id = pg.physical_game
            UNION
            SELECT g.id, g.name, g.console
            FROM physical_games g
            JOIN wanted_games w ON g.id = w.physical_game
        )
        SELECT
            g.name,
            g.console,
            z.pricecharting_id,
            max(p.retrieve_time) as retrieve_time,
            p.price,
            p.condition
        FROM base_games g
        JOIN physical_games_pricecharting_games j
            ON g.id = j.physical_game
        JOIN pricecharting_games z
            ON j.pricecharting_game = z.id
        LEFT JOIN pricecharting_prices p
            ON z.pricecharting_id = p.pricecharting_id
        GROUP BY g.id, p.condition
        ORDER BY g.name ASC;

        CREATE VIEW IF NOT EXISTS eligible_price_updates AS
        WITH latest_updates AS (
            -- Get the most recent update time for each game, even if prices were null
            SELECT 
                pricecharting_id,
                MAX(retrieve_time) as last_update
            FROM pricecharting_prices
            GROUP BY pricecharting_id
        )
        SELECT DISTINCT
            g.name,
            g.console,
            z.pricecharting_id
        FROM physical_games g
        LEFT JOIN purchased_games pg
            ON g.id = pg.physical_game
        JOIN physical_games_pricecharting_games j
            ON g.id = j.physical_game
        JOIN pricecharting_games z
            ON j.pricecharting_game = z.id
        LEFT JOIN latest_updates lu
            ON z.pricecharting_id = lu.pricecharting_id
        WHERE lu.last_update IS NULL  -- Never attempted
           OR datetime(lu.last_update) < datetime('now', '-7 days')  -- Or old attempt (even if it was null)
        ORDER BY g.name ASC;
    """)

    # Commit changes to ensure views are updated
    db_connection.commit()

    # Test retrieving all eligible games (no limit)
    games = retrieve_games(db_connection)
    assert len(games) == 3  # Should get games A, B, and C
    assert all(id in games for id in ['1001', '1002', '1003'])

    # Test retrieving with max_prices=2
    games = retrieve_games(db_connection, max_prices=2)
    assert len(games) == 2

    # Test retrieving with max_prices=0
    games = retrieve_games(db_connection, max_prices=0)
    assert len(games) == 0

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
    assert len(games) == 0

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