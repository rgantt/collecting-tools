#!/usr/local/bin/python3

import argparse
import sqlite3
from typing import Callable, List
import json
from price_retrieval import retrieve_games, process_batch, insert_price_records
from id_retrieval import retrieve_games, get_game_id, insert_game_ids
from datetime import datetime

class GameLibrary:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._commands: List[tuple[str, Callable]] = []
        self.register_commands()

    def _validate_date(self, date_str: str) -> bool:
        """Validate that a string is a proper ISO-8601 date (YYYY-MM-DD)."""
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    def _get_valid_date(self, prompt: str, current_value: str = None) -> str:
        """Get a valid ISO-8601 date from user input."""
        while True:
            display = f" [{current_value}]" if current_value else ""
            try:
                date_input = input(f"{prompt}{display}: ").strip()
                
                # Allow empty input when editing
                if current_value and not date_input:
                    return current_value
                
                if not date_input:
                    print("Date is required. Format: YYYY-MM-DD")
                    continue
                
                if not self._validate_date(date_input):
                    print("Invalid date format. Please use YYYY-MM-DD (e.g., 2024-03-15)")
                    continue
                
                return date_input
            
            except EOFError:
                raise

    def register_commands(self):
        self.register("Exit", self.exit)
        self.register("Add a game to your library", self.add_game)
        self.register("Retrieve latest prices", self.retrieve_prices)
        self.register("Retrieve missing game IDs", self.retrieve_ids)
        self.register("Edit existing game", self.edit_game)

    def register(self, description: str, command: Callable):
        self._commands.append((description, command))

    def display_commands(self):
        print("\nAvailable commands:")
        for num, (desc, _) in enumerate(self._commands):
            print(f"[{num}] - {desc}")
        print()

    def execute_command(self, number: int):
        if 0 <= number < len(self._commands):
            _, command = self._commands[number]
            command()
            return True
        return False

    def exit(self):
        raise SystemExit

    def add_game(self):
        print("We'll add game to the library interactively. I need some info from you.")

        try:
            game_data = {
                'title': input('Title: '),
                'console': input('Console: '),
                'condition': input('Condition: '),
                'source': input('Source: '),
                'price': input('Price: '),
                'date': self._get_valid_date('Date')
            }
        except EOFError:
            print("\nInput cancelled")
            return

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

    def retrieve_prices(self):
        try:
            batch_size = int(input('Batch size (default 50): ') or '50')
            max_prices = input('Maximum prices to retrieve (optional): ')
            max_prices = int(max_prices) if max_prices else None
        except (ValueError, EOFError):
            print("\nInvalid input")
            return

        games = retrieve_games(self.db_path, max_prices)
        if not games:
            print("No games found needing price updates.")
            return

        print(f"Retrieving prices for {len(games)} games...")
        all_failed = []
        processed = 0

        for i in range(0, len(games), batch_size):
            batch = games[i:i + batch_size]
            successful, failed = process_batch(batch)
            
            if successful:
                try:
                    insert_price_records(successful, self.db_path)
                    processed += len(successful)
                    print(f"Progress: {processed}/{len(games)} prices retrieved")
                except sqlite3.Error as e:
                    print(f"Failed to save batch to database: {e}")
            
            all_failed.extend(failed)
        
        print(f"Completed: {processed}/{len(games)} prices retrieved")
        
        if all_failed:
            print(f"\nFailures ({len(all_failed)}):")
            print(json.dumps(all_failed, indent=2))

    def retrieve_ids(self):
        games = retrieve_games(self.db_path)
        if not games:
            print("No unidentified games found.")
            return

        print(f"Retrieving identifiers for {len(games)} games:")

        failed = []
        retrieved = []
        for id, name, console in games:
            try:
                print(f"{name} on {console}...")
                data = get_game_id(id, name, console)
                retrieved.append(data)
            except ValueError as err:
                msg = f"Could not retrieve info: {err}"
                failed.append({'game': id, 'name': name, 'message': msg})
        
        if retrieved:
            try:
                records_inserted = insert_game_ids(retrieved, self.db_path)
                print(f"Saved {records_inserted} records to database")
            except sqlite3.Error as e:
                print(f"Failed to save records to database: {e}")

        if failed:
            print("\nFailures:")
            print(json.dumps(failed, indent=2))

    def edit_game(self):
        try:
            search_name = input('Enter game name to search for: ')
        except EOFError:
            print("\nInput cancelled")
            return

        try:
            with sqlite3.connect(self.db_path) as con:
                cursor = con.execute("""
                    SELECT 
                        p.id,
                        p.name,
                        p.console,
                        p.condition,
                        p.source,
                        p.price,
                        p.acquisition_date
                    FROM physical_games p
                    WHERE p.name LIKE ?
                    ORDER BY p.name
                """, (f"%{search_name}%",))
                
                games = cursor.fetchall()
                
                if not games:
                    print("No games found matching that name.")
                    return

                print("\nFound games:")
                for i, (id, name, console, condition, source, price, date) in enumerate(games):
                    print(f"[{i}] {name} ({console}) - {condition} condition, {price} from {source} on {date}")

                try:
                    choice = int(input('\nSelect game to edit (or Ctrl+D to cancel): '))
                    if not 0 <= choice < len(games):
                        print("Invalid selection")
                        return
                except (ValueError, EOFError):
                    print("\nInput cancelled")
                    return

                game_id = games[choice][0]
                print("\nEnter new values (or press Enter to keep current value)")
                
                try:
                    updates = {}
                    name = input(f'Name [{games[choice][1]}]: ').strip()
                    if name:
                        updates['name'] = name
                    
                    console = input(f'Console [{games[choice][2]}]: ').strip()
                    if console:
                        updates['console'] = console
                    
                    condition = input(f'Condition [{games[choice][3]}]: ').strip()
                    if condition:
                        updates['condition'] = condition
                    
                    source = input(f'Source [{games[choice][4]}]: ').strip()
                    if source:
                        updates['source'] = source
                    
                    price = input(f'Price [{games[choice][5]}]: ').strip()
                    if price:
                        updates['price'] = price
                    
                    date = self._get_valid_date('Date', games[choice][6])
                    if date != games[choice][6]:
                        updates['acquisition_date'] = date

                except EOFError:
                    print("\nInput cancelled")
                    return

                if not updates:
                    print("No changes made")
                    return

                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [game_id]
                
                cursor.execute(f"""
                    UPDATE physical_games
                    SET {set_clause}
                    WHERE id = ?
                """, values)

                if updates.get('name') or updates.get('console'):
                    cursor.execute("""
                        UPDATE pricecharting_games
                        SET name = COALESCE(?, name),
                            console = COALESCE(?, console)
                        WHERE id IN (
                            SELECT pricecharting_game
                            FROM physical_games_pricecharting_games
                            WHERE physical_game = ?
                        )
                    """, (updates.get('name'), updates.get('console'), game_id))

                print("Changes saved")

        except sqlite3.Error as e:
            print(f"Database error: {e}")

def main():
    parser = argparse.ArgumentParser(description='Add games to your library')
    parser.add_argument('-d', '--db', required=True, help='Path to SQLite database')
    args = parser.parse_args()

    library = GameLibrary(args.db)
    
    while True:
        library.display_commands()
        try:
            action = int(input('What would you like to do? '))
            if not library.execute_command(action):
                print(f"{action} is not a valid option")

        except ValueError:
            print("Please enter a valid number")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

if __name__ == '__main__':
    main()
