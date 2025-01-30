import pytest
from unittest.mock import Mock, patch
import datetime
import sqlite3
from bs4 import BeautifulSoup
from lib.price_retrieval import get_game_prices, insert_price_records

def test_null_price_handling(tmp_path):
    # Create a test database
    db_path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as con:
        # Create the pricecharting_games table first
        con.execute("""
            CREATE TABLE pricecharting_games (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)
        
        # Create the prices table with foreign key
        con.execute("""
            CREATE TABLE pricecharting_prices (
                pricecharting_id TEXT NOT NULL,
                retrieve_time TEXT NOT NULL,
                price REAL,
                condition TEXT NOT NULL,
                FOREIGN KEY(pricecharting_id) REFERENCES pricecharting_games(id)
            )
        """)
        
        # Insert a test game record
        con.execute("""
            INSERT INTO pricecharting_games (id, name) 
            VALUES (?, ?)
        """, ('test123', 'Test Game'))
        
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
        
        # Insert the record
        insert_price_records([result], db_path)
        
        # Verify records were inserted with null prices
        with sqlite3.connect(db_path) as con:
            cursor = con.execute("""
                SELECT pricecharting_id, price, condition
                FROM pricecharting_prices
                WHERE pricecharting_id = ?
                ORDER BY condition
            """, (game_id,))
            records = cursor.fetchall()
            
            # Should have records for all conditions with null prices
            assert len(records) == 4
            conditions = [r[2] for r in records]
            assert sorted(conditions) == ['complete', 'loose', 'new', 'new']
            assert all(r[1] is None for r in records)  # all prices should be null 