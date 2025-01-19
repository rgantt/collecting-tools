#!/usr/local/bin/python3

import argparse
import sqlite3

def display_actions():
    print("""
[0] - Exit
[1] - Add a game to your library
""")

def add_game(db_path):
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
        with sqlite3.connect(db_path) as con:
            cursor = con.cursor()
            
            # Insert physical game record
            cursor.execute("""
                INSERT INTO physical_games
                (acquisition_date, source, price, name, console, condition)
                VALUES (?,?,?,?,?,?)
            """, (game_data['date'], game_data['source'], game_data['price'], 
                  game_data['title'], game_data['console'], game_data['condition']))
            physical_id = cursor.lastrowid

            # Insert pricecharting record
            cursor.execute("""
                INSERT INTO pricecharting_games
                (name, console)
                VALUES (?,?)
            """, (game_data['title'], game_data['console']))
            pricecharting_id = cursor.lastrowid

            # Link the records
            cursor.execute("""
                INSERT INTO physical_games_pricecharting_games
                (physical_game, pricecharting_game)
                VALUES (?,?)
            """, (physical_id, pricecharting_id))
            
            print("Committed")
    except sqlite3.Error as e:
        print(f"Database error: {e}")

def main():
    parser = argparse.ArgumentParser(description='Add games to your library')
    parser.add_argument('-d', '--db', required=True, help='Path to SQLite database')
    args = parser.parse_args()

    while True:
        display_actions()

        try:
            action = int(input('What would you like to do? '))
            match action:
                case 0:
                    break
                case 1:
                    add_game(args.db)
                case _:
                    print(f"{action} is not a valid option")
        except ValueError:
            print("Please enter a valid number")

if __name__ == '__main__':
    main()
            
