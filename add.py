#!/usr/local/bin/python3

import argparse
import sqlite3
from typing import Callable, List

class GameLibrary:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.commands: List[tuple[str, Callable]] = []
        self.register_commands()

    def register_commands(self):
        self.register("Exit", self.exit)
        self.register("Add a game to your library", self.add_game)

    def register(self, description: str, command: Callable):
        self.commands.append((description, command))

    def display_commands(self):
        print("\nAvailable commands:")
        for num, (desc, _) in enumerate(self.commands):
            print(f"[{num}] - {desc}")
        print()

    def exit(self):
        raise SystemExit

    def add_game(self):
        print("We'll add game to the library interactively. I need some info from you.")

        game_data = {
            'title': input('Title: '),
            'console': input('Console: '),
            'condition': input('Condition: '),
            'source': input('Source: '),
            'price': input('Price: '),
            'date': input('Date: ')
        }

        try:
            with sqlite3.connect(self.db_path) as con:
                cursor = con.cursor()
                
                cursor.execute("""
                    INSERT INTO physical_games
                    (acquisition_date, source, price, name, console, condition)
                    VALUES (?,?,?,?,?,?)
                """, (game_data['date'], game_data['source'], game_data['price'], 
                      game_data['title'], game_data['console'], game_data['condition']))
                physical_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO pricecharting_games
                    (name, console)
                    VALUES (?,?)
                """, (game_data['title'], game_data['console']))
                pricecharting_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO physical_games_pricecharting_games
                    (physical_game, pricecharting_game)
                    VALUES (?,?)
                """, (physical_id, pricecharting_id))
                
                print("Committed")
        except sqlite3.Error as e:
            print(f"Database error: {e}")

    def run(self):
        
        while True:
            self.display_commands()

            try:
                action = int(input('What would you like to do? '))
                if not 0 <= action < len(self.commands):
                    print(f"{action} is not a valid option")
                    continue

                _, command = self.commands[action]
                command()

            except ValueError:
                print("Please enter a valid number")

def main():
    parser = argparse.ArgumentParser(description='Add games to your library')
    parser.add_argument('-d', '--db', required=True, help='Path to SQLite database')
    args = parser.parse_args()

    library = GameLibrary(args.db)
    library.run()

if __name__ == '__main__':
    main()
