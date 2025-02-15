import json
import os
import sqlite3
from pathlib import Path
import pytest
from datetime import datetime, timedelta
from collection import GameData, GameLibrary

from lib.collection_utils import (
    add_game_to_database,
    add_game_to_wishlist,
    get_collection_value_stats,
    get_console_distribution,
    get_recent_additions,
    get_wishlist_items,
    remove_from_wishlist,
    search_games
)
from lib.price_retrieval import insert_price_records

@pytest.fixture
def db_connection():
    """Create a temporary in-memory SQLite database for testing.
    
    The database is initialized with the schema from schema/collection.sql.
    The connection is automatically closed after the test completes.
    Foreign key constraints are enabled.
    
    Yields:
        sqlite3.Connection: A connection to the in-memory database.
    """
    conn = sqlite3.connect(':memory:')
    conn.execute("PRAGMA foreign_keys = ON")
    
    with open('schema/collection.sql', 'r') as f:
        conn.executescript(f.read())
    
    yield conn
    conn.close()

@pytest.fixture
def initialized_library(tmp_path, monkeypatch):
    """Create a GameLibrary instance with an initialized database."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr('builtins.input', lambda _: 'y')  # Auto-confirm initialization
    library = GameLibrary(str(db_path))
    return library

def test_add_game_to_database_basic(db_connection):
    """Test adding a game to the database."""
    game = GameData(
        title="Test Game",
        console="Test Console",
        condition="New",
        source="Test Store",
        price="49.99",
        date="2024-03-15"
    )
    
    result = add_game_to_database(db_connection, game)
    
    assert result.success
    assert result.game_id is not None
    assert "Game added successfully" in result.message
    
    # Verify the game was added correctly
    cursor = db_connection.cursor()
    cursor.execute("SELECT name, console FROM physical_games WHERE id = ?", (result.game_id,))
    game_record = cursor.fetchone()
    assert game_record[0] == "Test Game"
    assert game_record[1] == "Test Console"

def test_add_game_to_database_with_price_tracking(db_connection):
    """Test adding a game to the database with price tracking."""
    game = GameData(
        title="Test Game",
        console="Test Console",
        condition="New",
        source="Test Store",
        price="49.99",
        date="2024-03-15"
    )
    
    id_data = {
        "name": "Test Game",
        "console": "Test Console",
        "pricecharting_id": "TEST123"
    }
    
    result = add_game_to_database(db_connection, game, id_data)
    
    assert result.success
    assert result.game_id is not None
    assert "with price tracking enabled" in result.message
    
    # Verify price tracking data was added
    cursor = db_connection.cursor()
    cursor.execute("""
        SELECT pc.pricecharting_id 
        FROM physical_games_pricecharting_games pg_pc
        JOIN pricecharting_games pc ON pg_pc.pricecharting_game = pc.id
        WHERE pg_pc.physical_game = ?
    """, (result.game_id,))
    
    price_tracking = cursor.fetchone()
    assert price_tracking[0] == "TEST123"

def test_add_game_to_wishlist(db_connection):
    """Test adding a game to the wishlist."""
    result = add_game_to_wishlist(db_connection, "Test Game", "Test Console")
    
    assert result.success
    assert result.game_id is not None
    
    # Verify game was added to wishlist
    cursor = db_connection.cursor()
    cursor.execute("""
        SELECT p.name, p.console 
        FROM physical_games p
        JOIN wanted_games w ON p.id = w.physical_game
        WHERE p.id = ?
    """, (result.game_id,))
    
    wishlist_game = cursor.fetchone()
    assert wishlist_game[0] == "Test Game"
    assert wishlist_game[1] == "Test Console"

def test_get_console_distribution(db_connection):
    """Test getting the console distribution."""
    # Add some test data
    cursor = db_connection.cursor()
    cursor.execute("INSERT INTO physical_games (name, console) VALUES (?, ?)", ("Game 1", "Console A"))
    game1_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO purchased_games 
        (physical_game, condition, price, acquisition_date) 
        VALUES (?, ?, ?, ?)
    """, (game1_id, "New", "49.99", "2024-03-15"))
    
    cursor.execute("INSERT INTO physical_games (name, console) VALUES (?, ?)", ("Game 2", "Console A"))
    game2_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO purchased_games 
        (physical_game, condition, price, acquisition_date) 
        VALUES (?, ?, ?, ?)
    """, (game2_id, "New", "29.99", "2024-03-15"))
    
    cursor.execute("INSERT INTO physical_games (name, console) VALUES (?, ?)", ("Game 3", "Console B"))
    game3_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO purchased_games 
        (physical_game, condition, price, acquisition_date) 
        VALUES (?, ?, ?, ?)
    """, (game3_id, "Used", "19.99", "2024-03-15"))
    
    distributions = get_console_distribution(db_connection)
    
    assert len(distributions) == 2
    console_a = next(d for d in distributions if d.console == "Console A")
    assert console_a.game_count == 2
    assert console_a.percentage == 66.7  # 2/3 * 100
    
    console_b = next(d for d in distributions if d.console == "Console B")
    assert console_b.game_count == 1
    assert console_b.percentage == 33.3  # 1/3 * 100

def test_get_recent_additions(db_connection):
    """Test getting recent additions."""
    # Add some test data
    cursor = db_connection.cursor()
    
    # Add a purchased game
    cursor.execute("INSERT INTO physical_games (name, console) VALUES (?, ?)", ("Recent Game", "Console A"))
    game_id = cursor.lastrowid
    cursor.execute("""
        INSERT INTO purchased_games 
        (physical_game, condition, price, acquisition_date, source) 
        VALUES (?, ?, ?, ?, ?)
    """, (game_id, "New", "49.99", "2024-03-15", "Test Store"))
    
    # Add a wishlist game
    cursor.execute("INSERT INTO physical_games (name, console) VALUES (?, ?)", ("Wanted Game", "Console B"))
    wanted_id = cursor.lastrowid
    cursor.execute("INSERT INTO wanted_games (physical_game) VALUES (?)", (wanted_id,))
    
    recent = get_recent_additions(db_connection)
    
    assert len(recent) == 2
    
    # Check purchased game
    purchased = next(r for r in recent if not r.is_wanted)
    assert purchased.name == "Recent Game"
    assert purchased.console == "Console A"
    assert purchased.condition == "New"
    assert purchased.price == 49.99
    assert purchased.date == "2024-03-15"
    
    # Check wishlist game
    wanted = next(r for r in recent if r.is_wanted)
    assert wanted.name == "Wanted Game"
    assert wanted.console == "Console B"
    assert wanted.is_wanted

def test_price_retrieval_and_storage(db_connection):
    """Test that retrieved prices are correctly saved and marked as up-to-date."""
    cursor = db_connection.cursor()
    
    # Add physical game
    cursor.execute("""
        INSERT INTO physical_games (name, console)
        VALUES (?, ?)
    """, ('Test Game', 'Test Console'))
    physical_id = cursor.lastrowid
    
    # Add purchase details
    cursor.execute("""
        INSERT INTO purchased_games
        (physical_game, condition, source, price, acquisition_date)
        VALUES (?, ?, ?, ?, ?)
    """, (physical_id, 'complete', 'Test', '10.00', '2024-03-15'))
    
    # Add pricecharting game
    cursor.execute("""
        INSERT INTO pricecharting_games (name, console, pricecharting_id)
        VALUES (?, ?, ?)
    """, ('Test Game', 'Test Console', 'TEST123'))
    pc_id = cursor.lastrowid
    
    # Link physical and pricecharting games
    cursor.execute("""
        INSERT INTO physical_games_pricecharting_games
        (physical_game, pricecharting_game)
        VALUES (?, ?)
    """, (physical_id, pc_id))
    
    db_connection.commit()

    # Mock price data to be inserted with correct format
    test_prices = [{
        'game': 'TEST123',  # This should be the pricecharting_id
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'prices': {
            'complete': 20.00,
            'loose': 15.00,
            'new': 30.00
        }
    }]
    
    # Insert prices directly using the connection
    records = [
        (record['game'], record['time'], record['prices'][condition], condition)
        for record in test_prices
        for condition, price in record['prices'].items()
        if price is not None
    ]
    
    cursor.executemany("""
        INSERT INTO pricecharting_prices
        (pricecharting_id, retrieve_time, price, condition)
        VALUES (?,?,?,?)
    """, records)
    
    db_connection.commit()
    
    # Check if prices exist and are recent
    cursor.execute("""
        SELECT pricecharting_id, condition, price, retrieve_time
        FROM pricecharting_prices
        WHERE pricecharting_id = 'TEST123'
        ORDER BY retrieve_time DESC
    """)
    
    prices = cursor.fetchall()
    assert len(prices) == 3  # Should have 3 conditions
    
    # Check each condition has a price
    conditions = set()
    for price in prices:
        pricecharting_id, condition, price_value, retrieve_time = price
        conditions.add(condition)
        assert pricecharting_id == 'TEST123'
        assert price_value is not None
        # Verify retrieve_time is recent (within last minute)
        retrieve_datetime = datetime.strptime(retrieve_time, '%Y-%m-%d %H:%M:%S')
        assert datetime.now() - retrieve_datetime < timedelta(minutes=1)
    
    assert conditions == {'complete', 'loose', 'new'}
    
    # Verify game is not eligible for update
    cursor.execute("""
        SELECT COUNT(DISTINCT pricecharting_id)
        FROM latest_prices
        WHERE retrieve_time < datetime('now', '-7 days')
        OR retrieve_time IS NULL
    """)
    eligible_count = cursor.fetchone()[0]
    assert eligible_count == 0 

def test_game_library_add_game(tmp_path, monkeypatch):
    """Test the interactive add_game method of GameLibrary."""
    # Create a temporary database file
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    with open('schema/collection.sql', 'r') as f:
        conn.executescript(f.read())
    conn.close()
    
    # Mock user input for game details and choice
    inputs = iter([
        "Test Game",  # title
        "Switch",     # console
        "new",       # condition
        "Amazon",    # source
        "59.99",     # price
        "2025-01-30", # date
        "c"          # choice to continue without price tracking
    ])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))
    
    # Mock get_game_id to simulate price tracking ID retrieval failure
    def mock_get_game_id(*args):
        raise ValueError("Price tracking unavailable")
    monkeypatch.setattr('collection.get_game_id', mock_get_game_id)
    
    # Create GameLibrary instance with test database
    library = GameLibrary(db_path)
    
    # Add the game
    library.add_game()
    
    # Verify the game was added
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pg.name, pg.console, pur.condition, pur.source, pur.price, pur.acquisition_date
            FROM physical_games pg
            JOIN purchased_games pur ON pg.id = pur.physical_game
            WHERE pg.name = 'Test Game'
        """)
        game = cursor.fetchone()
        
        assert game is not None
        assert game[0] == "Test Game"
        assert game[1] == "Switch"
        assert game[2] == "new"
        assert game[3] == "Amazon"
        assert float(game[4]) == 59.99  # Compare as float
        assert game[5] == "2025-01-30"

def test_search_games(initialized_library, monkeypatch):
    """Test searching games in the collection."""
    # Mock get_game_id to avoid HTTP requests
    def mock_get_game_id(internal_id, game_name, system_name):
        raise ValueError("Mocked error")
    monkeypatch.setattr('lib.id_retrieval.get_game_id', mock_get_game_id)

    # Add test games
    game1_data = {
        'title': 'Super Mario 64',
        'console': 'N64',
        'condition': 'loose',
        'source': 'eBay',
        'price': '45.99',
        'date': '2024-03-15'
    }
    game2_data = {
        'title': 'Mario Kart 8 Deluxe',
        'console': 'Switch',
        'condition': 'complete',
        'source': 'GameStop',
        'price': '39.99',
        'date': '2024-02-01'
    }
    wishlist_data = {
        'title': 'Super Mario RPG',
        'console': 'Switch'
    }

    def mock_input(prompt: str) -> str:
        if 'Would you like to (e)dit the game info, or (c)ontinue without price tracking?' in prompt:
            return 'c'
        elif 'Title' in prompt:
            if '[' not in prompt:  # First input for each game
                if not hasattr(mock_input, 'current_game'):
                    mock_input.current_game = 'game1'
                    return game1_data['title']
                elif mock_input.current_game == 'game1':
                    mock_input.current_game = 'game2'
                    return game2_data['title']
                elif mock_input.current_game == 'game2':
                    mock_input.current_game = 'wishlist'
                    return wishlist_data['title']
                else:
                    return 'mario'  # For search
        elif 'Console' in prompt:
            if mock_input.current_game == 'game1':
                return game1_data['console']
            elif mock_input.current_game == 'game2':
                return game2_data['console']
            elif mock_input.current_game == 'wishlist':
                return wishlist_data['console']
        elif 'Condition' in prompt:
            if mock_input.current_game == 'game1':
                return game1_data['condition']
            elif mock_input.current_game == 'game2':
                return game2_data['condition']
        elif 'Source' in prompt:
            if mock_input.current_game == 'game1':
                return game1_data['source']
            elif mock_input.current_game == 'game2':
                return game2_data['source']
        elif 'Price' in prompt:
            if mock_input.current_game == 'game1':
                return game1_data['price']
            elif mock_input.current_game == 'game2':
                return game2_data['price']
        elif 'Date' in prompt:
            if mock_input.current_game == 'game1':
                return game1_data['date']
            elif mock_input.current_game == 'game2':
                return game2_data['date']
        elif 'Enter search term' in prompt:
            return 'mario'
        return ''

    monkeypatch.setattr('builtins.input', mock_input)

    # Add games and wishlist item
    initialized_library.add_game()
    initialized_library.add_game()
    initialized_library.want_game()

    # Test search functionality
    with initialized_library._db_connection() as conn:
        results = search_games(conn, 'mario')
        assert len(results) == 3
        assert any(g.name == "Super Mario 64" and g.console == "N64" for g in results)
        assert any(g.name == "Mario Kart 8 Deluxe" and g.console == "Switch" for g in results)
        assert any(g.name == "Super Mario RPG" and g.console == "Switch" and g.is_wanted for g in results)

def test_wishlist_view_and_edit(initialized_library, monkeypatch):
    """Test viewing and editing the wishlist."""
    # Mock get_game_id to avoid HTTP requests
    def mock_get_game_id(internal_id, game_name, system_name):
        raise ValueError("Mocked error")
    monkeypatch.setattr('lib.id_retrieval.get_game_id', mock_get_game_id)

    # Add test wishlist items
    wishlist1_data = {
        'title': 'Super Mario RPG',
        'console': 'Switch'
    }
    wishlist2_data = {
        'title': 'Mario Kart 9',
        'console': 'Switch'
    }

    def mock_input(prompt: str) -> str:
        if 'Would you like to (e)dit the game info, or (c)ontinue without price tracking?' in prompt:
            return 'c'
        elif 'Title' in prompt:
            if '[' not in prompt:  # First input for each game
                if not hasattr(mock_input, 'current_game'):
                    mock_input.current_game = 'wishlist1'
                    return wishlist1_data['title']
                elif mock_input.current_game == 'wishlist1':
                    mock_input.current_game = 'wishlist2'
                    return wishlist2_data['title']
                else:
                    mock_input.current_game = 'search'
                    return 'mario'
        elif 'Console' in prompt:
            if mock_input.current_game == 'wishlist1':
                return wishlist1_data['console']
            elif mock_input.current_game == 'wishlist2':
                return wishlist2_data['console']
        elif 'Enter search term' in prompt:
            return 'mario'
        elif 'Select a game to edit' in prompt:
            return '1'
        elif 'Choose an option (1-3)' in prompt:
            return '1'  # Choose delete option
        elif 'Are you sure you want to delete this game?' in prompt:
            return 'y'
        return ''

    monkeypatch.setattr('builtins.input', mock_input)
    
    # Add wishlist items
    initialized_library.want_game()
    initialized_library.want_game()
    
    # Test viewing and editing wishlist
    initialized_library.view_wishlist()
    
    # Verify game was removed
    with initialized_library._db_connection() as conn:
        remaining_items = get_wishlist_items(conn)
        assert len(remaining_items) == 1
        assert all(item.name != "Super Mario RPG" for item in remaining_items)

def test_value_statistics(db_connection):
    """Test collection value statistics."""
    # Add test games with known values
    games = [
        GameData(
            title="Earthbound",
            console="SNES",
            condition="complete",
            source="eBay",
            price="299.99",
            date="2024-01-01"
        ),
        GameData(
            title="Chrono Trigger",
            console="SNES",
            condition="complete",
            source="Local Store",
            price="275.00",
            date="2024-01-15"
        )
    ]
    
    for game in games:
        result = add_game_to_database(db_connection, game)
        
        # Add price tracking data
        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO pricecharting_games (pricecharting_id, name, console)
            VALUES (?, ?, ?)
        """, (f"test-{game.title.lower()}", game.title, game.console))
        pc_id = cursor.lastrowid
        
        # Link the game to price tracking
        cursor.execute("""
            INSERT INTO physical_games_pricecharting_games (physical_game, pricecharting_game)
            VALUES (?, ?)
        """, (result.game_id, pc_id))
        
        # Add current prices
        cursor.execute("""
            INSERT INTO pricecharting_prices (pricecharting_id, condition, price, retrieve_time)
            VALUES (?, ?, ?, ?)
        """, (f"test-{game.title.lower()}", game.condition.lower(), 
              "399.99" if game.title == "Earthbound" else "349.99", 
              "2024-03-15"))

    stats = get_collection_value_stats(db_connection)
    
    assert stats.total_purchase == 574.99  # 299.99 + 275.00
    assert stats.total_market == 749.98    # 399.99 + 349.99
    assert len(stats.top_valuable) == 2
    assert stats.top_valuable[0][0] == "Earthbound"  # Most valuable game
    assert float(stats.top_valuable[0][4]) == 399.99  # Current price

def test_help_command(initialized_library, capsys):
    """Test the help command output."""
    initialized_library.display_commands()
    captured = capsys.readouterr()
    
    # Verify all commands are listed
    assert "add" in captured.out
    assert "search" in captured.out
    assert "prices" in captured.out
    assert "want" in captured.out
    assert "wishlist" in captured.out
    assert "value" in captured.out
    assert "distribution" in captured.out
    assert "recent" in captured.out
    assert "help" in captured.out

def test_recent_additions_with_prices(db_connection):
    """Test displaying recent additions with price information."""
    # Add a recent game
    game = GameData(
        title="Final Fantasy XVI",
        console="PS5",
        condition="new",
        source="Amazon",
        price="69.99",
        date=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    )
    result = add_game_to_database(db_connection, game)
    
    # Add price tracking data
    cursor = db_connection.cursor()
    cursor.execute("""
        INSERT INTO pricecharting_games (pricecharting_id, name, console)
        VALUES ('test-ff16', 'Final Fantasy XVI', 'PS5')
    """)
    pc_id = cursor.lastrowid
    
    cursor.execute("""
        INSERT INTO physical_games_pricecharting_games (physical_game, pricecharting_game)
        VALUES (?, ?)
    """, (result.game_id, pc_id))
    
    cursor.execute("""
        INSERT INTO pricecharting_prices (pricecharting_id, condition, price, retrieve_time)
        VALUES ('test-ff16', 'new', '54.99', '2024-03-15')
    """)
    
    # Add a recent wishlist item
    wishlist_result = add_game_to_wishlist(db_connection, "Persona 3 Reload", "PS5")
    
    # Test recent additions
    recent = get_recent_additions(db_connection)
    
    # Check collection additions
    collection_items = [item for item in recent if not item.is_wanted]
    assert len(collection_items) >= 1
    ff16 = next(item for item in collection_items if item.name == "Final Fantasy XVI")
    assert ff16.console == "PS5"
    assert ff16.condition == "new"
    assert ff16.source == "Amazon"
    assert float(ff16.price) == 69.99
    assert ff16.current_prices.get('new') == 54.99
    
    # Check wishlist additions
    wishlist_items = [item for item in recent if item.is_wanted]
    assert len(wishlist_items) >= 1
    assert any(item.name == "Persona 3 Reload" and item.console == "PS5" for item in wishlist_items)

def test_end_to_end_game_management(initialized_library, monkeypatch):
    """Test end-to-end flow of adding, searching, and editing a game in the collection."""
    # Mock user inputs for adding a game
    add_inputs = iter([
        "The Legend of Zelda: Tears of the Kingdom",  # title
        "Switch",     # console
        "new",       # condition
        "GameStop",   # source
        "69.99",     # price
        "2025-02-11", # date
        "c"          # choice to continue without price tracking
    ])
    monkeypatch.setattr('builtins.input', lambda _: next(add_inputs))

    # Add the game
    initialized_library.add_game()

    # Mock user inputs for searching and editing the game
    search_edit_inputs = iter([
        "Tears of the Kingdom",  # search term
        "0",                     # select first game
        "2",                     # choose update option
        "Zelda: Tears of the Kingdom",  # updated name
        "",                      # keep same console
        "used",                  # new condition
        "",                      # keep same source
        "54.99",                # new price
        "",                     # keep same date
    ])
    monkeypatch.setattr('builtins.input', lambda _: next(search_edit_inputs))

    # Search and edit the game
    initialized_library.search_library()

    # Verify the changes
    with initialized_library._db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pg.name, pg.console, p.condition, p.source, p.price, p.acquisition_date
            FROM physical_games pg
            JOIN purchased_games p ON pg.id = p.physical_game
            WHERE pg.name LIKE ?
        """, ('%Tears of the Kingdom%',))
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "Zelda: Tears of the Kingdom"  # name
        assert result[1] == "Switch"                       # console
        assert result[2] == "used"                        # condition
        assert result[3] == "GameStop"                    # source
        assert round(float(result[4]), 2) == 54.99        # price
        assert result[5] == "2025-02-11"                  # date

def test_end_to_end_game_with_prices(initialized_library, monkeypatch):
    """Test end-to-end flow of adding a game with price information and finding it in search results."""
    # Mock user inputs for adding a game
    inputs = iter([
        "Super Mario 64",  # title
        "Nintendo 64",     # console
        "Good",           # condition
        "Local Store",    # source
        "39.99",         # price
        "2025-02-11",    # date (using current date)
        ""               # empty input to finish
    ])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))

    # Add a game with price tracking information
    with initialized_library._db_connection() as conn:
        game = GameData(
            title="Super Mario 64",
            console="Nintendo 64",
            condition="Good",
            source="Local Store",
            price="39.99",
            date="2025-02-11"
        )
        
        # Add game with price tracking ID
        id_data = {
            "name": "Super Mario 64",
            "console": "Nintendo 64",
            "pricecharting_id": "SM64-N64"
        }
        result = add_game_to_database(conn, game, id_data)
        assert result.success
        
        # Add a price record for the game
        price_data = {
            'game': 'SM64-N64',
            'time': '2025-02-11T00:00:00',
            'prices': {
                'loose': 39.99,
                'complete': 79.99,
                'new': 299.99
            }
        }
        insert_price_records([price_data], conn)
        
        # Search for the game
        search_results = search_games(conn, "Mario 64")
        
        # Verify game appears in search results with price information
        assert len(search_results) > 0
        found_game = next((game for game in search_results if game.name == "Super Mario 64"), None)
        assert found_game is not None
        assert found_game.name == "Super Mario 64"
        assert found_game.console == "Nintendo 64"
        assert found_game.condition == "Good"
        assert float(found_game.price) == 39.99
        assert found_game.current_prices is not None
        assert found_game.current_prices.get('loose') == 39.99
        assert found_game.current_prices.get('complete') == 79.99
        assert found_game.current_prices.get('new') == 299.99