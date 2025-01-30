import sqlite3
import pytest
from datetime import datetime
from collection import GameData, add_game_to_database, add_game_to_wishlist, get_console_distribution, get_recent_additions

@pytest.fixture
def db_connection():
    """Create an in-memory database for testing."""
    conn = sqlite3.connect(':memory:')
    with open('schema/collection.sql', 'r') as f:
        conn.executescript(f.read())
    return conn

def test_add_game_to_database_basic(db_connection):
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