import sqlite3
import pytest
from datetime import datetime
from lib.collection_utils import (
    WishlistItem, get_wishlist_items, update_wishlist_item,
    remove_from_wishlist, GameData, add_game_to_database, add_game_to_wishlist
)

@pytest.fixture
def db_connection():
    """Create an in-memory database for testing."""
    conn = sqlite3.connect(':memory:')
    with open('schema/collection.sql', 'r') as f:
        conn.executescript(f.read())
    return conn

@pytest.fixture
def sample_game(db_connection):
    """Add a sample game to the database and return its ID."""
    game = GameData(
        title="Test Game",
        console="Test Console",
        condition="New",
        source="Test Store",
        price="49.99",
        date=datetime.now().strftime("%Y-%m-%d")
    )
    result = add_game_to_database(db_connection, game)
    assert result.success
    return result.game_id

@pytest.fixture
def sample_wishlist_game(db_connection, sample_game):
    """Add a sample game to the wishlist."""
    cursor = db_connection.cursor()
    cursor.execute("INSERT INTO wanted_games (physical_game) VALUES (?)", (sample_game,))
    db_connection.commit()
    return sample_game

def test_get_wishlist_items_empty(db_connection):
    """Test getting wishlist items when the wishlist is empty."""
    items = get_wishlist_items(db_connection)
    assert len(items) == 0

def test_get_wishlist_items(db_connection, sample_wishlist_game):
    """Test getting wishlist items with a game in the wishlist."""
    items = get_wishlist_items(db_connection)
    assert len(items) == 1
    
    item = items[0]
    assert isinstance(item, WishlistItem)
    assert item.name == "Test Game"
    assert item.console == "Test Console"
    assert item.price_complete is None
    assert item.price_loose is None
    assert item.price_new is None

def test_get_wishlist_items_with_search(db_connection, sample_wishlist_game):
    """Test searching wishlist items."""
    # Should find the game
    items = get_wishlist_items(db_connection, "Test")
    assert len(items) == 1
    assert items[0].name == "Test Game"
    
    # Should not find any games
    items = get_wishlist_items(db_connection, "NonexistentGame")
    assert len(items) == 0

def test_get_wishlist_items_with_prices(db_connection, sample_wishlist_game):
    """Test getting wishlist items with price information."""
    # Add price tracking information
    cursor = db_connection.cursor()
    
    # Add pricecharting game
    cursor.execute("""
        INSERT INTO pricecharting_games (id, name, console, pricecharting_id)
        VALUES (?, ?, ?, ?)
    """, (1, "Test Game", "Test Console", 1))
    
    # Link physical game to pricecharting game
    cursor.execute("""
        INSERT INTO physical_games_pricecharting_games (physical_game, pricecharting_game)
        VALUES (?, ?)
    """, (sample_wishlist_game, 1))
    
    # Add some prices
    current_time = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO pricecharting_prices (pricecharting_id, condition, price, retrieve_time)
        VALUES
            (?, 'complete', 59.99, ?),
            (?, 'loose', 49.99, ?),
            (?, 'new', 69.99, ?)
    """, (1, current_time, 1, current_time, 1, current_time))
    
    db_connection.commit()
    
    # Get wishlist items and verify prices
    items = get_wishlist_items(db_connection)
    assert len(items) == 1
    
    item = items[0]
    assert item.price_complete == 59.99
    assert item.price_loose == 49.99
    assert item.price_new == 69.99

def test_get_wishlist_items_with_latest_prices(db_connection, sample_wishlist_game):
    """Test getting wishlist items with prices from latest_prices view."""
    cursor = db_connection.cursor()
    
    # Add pricecharting game
    cursor.execute("""
        INSERT INTO pricecharting_games (id, name, console, pricecharting_id)
        VALUES (?, ?, ?, ?)
    """, (1, "Test Game", "Test Console", 1))
    
    # Link physical game to pricecharting game
    cursor.execute("""
        INSERT INTO physical_games_pricecharting_games (physical_game, pricecharting_game)
        VALUES (?, ?)
    """, (sample_wishlist_game, 1))
    
    # Add multiple price records with different timestamps
    older_time = "2025-01-28T20:00:00.000000"
    newer_time = "2025-01-28T21:00:00.000000"
    
    # Add older prices
    cursor.execute("""
        INSERT INTO pricecharting_prices (pricecharting_id, condition, price, retrieve_time)
        VALUES
            (?, 'complete', 50.00, ?),
            (?, 'loose', 40.00, ?),
            (?, 'new', 60.00, ?)
    """, (1, older_time, 1, older_time, 1, older_time))
    
    # Add newer prices (these should be the ones that show up)
    cursor.execute("""
        INSERT INTO pricecharting_prices (pricecharting_id, condition, price, retrieve_time)
        VALUES
            (?, 'complete', 55.00, ?),
            (?, 'loose', 45.00, ?),
            (?, 'new', 65.00, ?)
    """, (1, newer_time, 1, newer_time, 1, newer_time))
    
    db_connection.commit()
    
    # Get wishlist items and verify we get the latest prices
    items = get_wishlist_items(db_connection)
    assert len(items) == 1
    
    item = items[0]
    assert item.name == "Test Game"
    assert item.console == "Test Console"
    assert item.pricecharting_id == "1"
    assert item.price_complete == 55.00  # Should get newer price
    assert item.price_loose == 45.00     # Should get newer price
    assert item.price_new == 65.00       # Should get newer price

def test_update_wishlist_item(db_connection, sample_wishlist_game):
    """Test updating a wishlist item."""
    updates = {
        'name': 'Updated Game',
        'console': 'Updated Console'
    }
    
    update_wishlist_item(db_connection, sample_wishlist_game, updates)
    
    # Verify updates in physical_games
    cursor = db_connection.cursor()
    cursor.execute("SELECT name, console FROM physical_games WHERE id = ?", (sample_wishlist_game,))
    game = cursor.fetchone()
    
    assert game[0] == "Updated Game"
    assert game[1] == "Updated Console"

def test_update_wishlist_item_with_pricecharting(db_connection, sample_wishlist_game):
    """Test updating a wishlist item that has pricecharting information."""
    # Add pricecharting game and link it
    cursor = db_connection.cursor()
    cursor.execute("""
        INSERT INTO pricecharting_games (id, name, console, pricecharting_id)
        VALUES (?, ?, ?, ?)
    """, (1, "Test Game", "Test Console", 1))
    
    cursor.execute("""
        INSERT INTO physical_games_pricecharting_games (physical_game, pricecharting_game)
        VALUES (?, ?)
    """, (sample_wishlist_game, 1))
    
    db_connection.commit()
    
    # Update the game
    updates = {
        'name': 'Updated Game',
        'console': 'Updated Console'
    }
    update_wishlist_item(db_connection, sample_wishlist_game, updates)
    
    # Verify updates in both tables
    cursor.execute("SELECT name, console FROM physical_games WHERE id = ?", (sample_wishlist_game,))
    physical_game = cursor.fetchone()
    assert physical_game[0] == "Updated Game"
    assert physical_game[1] == "Updated Console"
    
    cursor.execute("""
        SELECT name, console FROM pricecharting_games
        WHERE id IN (
            SELECT pricecharting_game
            FROM physical_games_pricecharting_games
            WHERE physical_game = ?
        )
    """, (sample_wishlist_game,))
    pricecharting_game = cursor.fetchone()
    assert pricecharting_game[0] == "Updated Game"
    assert pricecharting_game[1] == "Updated Console"

def test_remove_from_wishlist(db_connection, sample_wishlist_game):
    """Test removing a game from the wishlist."""
    # Verify game is in wishlist
    cursor = db_connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM wanted_games WHERE physical_game = ?", (sample_wishlist_game,))
    assert cursor.fetchone()[0] == 1
    
    # Remove from wishlist
    remove_from_wishlist(db_connection, sample_wishlist_game)
    
    # Verify game is removed from wishlist but still exists in physical_games
    cursor.execute("SELECT COUNT(*) FROM wanted_games WHERE physical_game = ?", (sample_wishlist_game,))
    assert cursor.fetchone()[0] == 0
    
    cursor.execute("SELECT COUNT(*) FROM physical_games WHERE id = ?", (sample_wishlist_game,))
    assert cursor.fetchone()[0] == 1
