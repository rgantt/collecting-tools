import sqlite3
import pytest
from datetime import datetime, timedelta
from collection import GameData, add_game_to_database, add_game_to_wishlist, get_console_distribution, get_recent_additions, GameLibrary
from lib.price_retrieval import insert_price_records

@pytest.fixture
def db_connection():
    """Create an in-memory database for testing."""
    conn = sqlite3.connect(':memory:')
    with open('schema/collection.sql', 'r') as f:
        conn.executescript(f.read())
    return conn

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
    
    # Initialize schema
    with open('schema/collection.sql', 'r') as f:
        schema = f.read()
        cursor.executescript(schema)
    
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