import os
import unittest
from library import GameLibrary
from unittest.mock import patch
import sqlite3

class TestGameLibrary(unittest.TestCase):
    def setUp(self):
        self.db_path = "test_games.db"
        # Ensure clean state
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        self.library = GameLibrary(self.db_path)

    def tearDown(self):
        # Clean up after test
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    @patch('builtins.input')
    def test_initialize_add_and_edit(self, mock_input):
        # Initialize DB
        mock_input.return_value = 'y'
        self.library.init_db()
        
        # Verify DB was created
        self.assertTrue(os.path.exists(self.db_path))
        
        # Add a game
        mock_input.side_effect = [
            'Super Mario Bros.',  # title
            'NES',               # console
            'Good',              # condition
            'eBay',              # source
            '45.00',             # price
            '2024-03-15'         # date
        ]
        self.library.add_game()
        
        # Verify game was added
        with sqlite3.connect(self.db_path) as con:
            cursor = con.execute("SELECT name, console FROM physical_games")
            game = cursor.fetchone()
            self.assertEqual(game[0], 'Super Mario Bros.')
            self.assertEqual(game[1], 'NES')
        
        # Edit the game
        mock_input.side_effect = [
            'Mario',             # search term
            '0',                 # select first result
            'Super Mario Bros. 1',  # new name
            '',                  # keep console
            '',                  # keep condition
            '',                  # keep source
            '',                  # keep price
            ''                   # keep date
        ]
        self.library.edit_game()
        
        # Verify game was updated
        with sqlite3.connect(self.db_path) as con:
            cursor = con.execute("SELECT name, console FROM physical_games")
            game = cursor.fetchone()
            self.assertEqual(game[0], 'Super Mario Bros. 1')
            self.assertEqual(game[1], 'NES')

if __name__ == '__main__':
    unittest.main() 