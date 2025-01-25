#!/usr/local/bin/python3

import argparse
import sqlite3
from typing import Callable, List
import json
from lib.price_retrieval import retrieve_games as retrieve_games_for_prices
from lib.price_retrieval import get_game_prices, insert_price_records
from lib.id_retrieval import retrieve_games as retrieve_games_for_ids
from lib.id_retrieval import get_game_id, insert_game_ids
from datetime import datetime

class GameLibrary:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._commands: List[tuple[str, str, Callable]] = []
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
        self.register("add", "Add a game to your library", self.add_game)
        self.register("search", "Search library", self.search_library)
        self.register("prices", "Retrieve latest prices", self.retrieve_prices)
        self.register("ids", "Retrieve missing game IDs", self.retrieve_ids)
        self.register("init", "Initialize new database", self.init_db)

    def register(self, command: str, description: str, func: Callable):
        self._commands.append((command, description, func))

    def display_commands(self):
        print("\nAvailable commands:")
        for command, desc, _ in self._commands:
            print(f"{command:8} - {desc}")
        print()

    def execute_command(self, command: str):
        command = command.lower().strip()
        for cmd, _, func in self._commands:
            if cmd == command:
                func()
                return True
        return False

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
            max_prices = input('Maximum prices to retrieve (optional): ')
            max_prices = int(max_prices) if max_prices else None
        except (ValueError, EOFError):
            print("\nInvalid input")
            return

        games = retrieve_games_for_prices(self.db_path, max_prices)
        if not games:
            print("No games found needing price updates.")
            return

        print(f"Retrieving prices for {len(games)} games...")
        all_failed = []
        processed = 0
        total = len(games)

        for i in range(0, len(games)):
            successful = []
            failed = []
            try:
                successful.append(get_game_prices(games[i]))
            except ValueError as err:
                failed.append({'game': games[i], 'message': str(err)})
                print(f"Error on game {games[i]}: {err}")
            
            if successful:
                try:
                    insert_price_records(successful, self.db_path)
                    processed += len(successful)
                    
                    # Calculate percentage and create progress bar
                    percent = (processed / total) * 100
                    bar_length = 50
                    filled = int(bar_length * processed // total)
                    bar = '=' * filled + '-' * (bar_length - filled)
                    
                    # Print progress on same line
                    print(f"\rProgress: [{bar}] {percent:.1f}% ({processed}/{total}) - {games[i]['name']}", end='', flush=True)
                    
                except sqlite3.Error as e:
                    print(f"\nFailed to save batch to database: {e}")
            
            all_failed.extend(failed)
        
        # Print newline after progress bar is complete
        print()
        print(f"Completed: {processed}/{len(games)} prices retrieved")
        
        if all_failed:
            print(f"\nFailures ({len(all_failed)}):")
            print(json.dumps(all_failed, indent=2))

    def retrieve_ids(self):
        games = retrieve_games_for_ids(self.db_path)
        if not games:
            print("No unidentified games found.")
            return

        print(f"Retrieving identifiers for {len(games)} games:")

        failed = []
        retrieved = []
        processed = 0
        total = len(games)
        
        for id, name, console in games:
            try:
                data = get_game_id(id, name, console)
                retrieved.append(data)
            except ValueError as err:
                msg = f"Could not retrieve info: {err}"
                failed.append({'game': id, 'name': name, 'message': msg})
            
            # Progress bar outside try/except
            processed += 1
            percent = (processed / total) * 100
            bar_length = 50
            filled = int(bar_length * processed // total)
            bar = '=' * filled + '-' * (bar_length - filled)
            print(f"\rProgress: [{bar}] {percent:.1f}% ({processed}/{total}) - {name}", end='', flush=True)
        
        # Print newline after progress bar is complete
        print()
        
        if retrieved:
            try:
                records_inserted = insert_game_ids(retrieved, self.db_path)
                print(f"Saved {records_inserted} records to database")
            except sqlite3.Error as e:
                print(f"Failed to save records to database: {e}")

        if failed:
            print("\nFailures:")
            print(json.dumps(failed, indent=2))

    def init_db(self):
        """Initialize a new database with the schema."""
        if input("This will initialize a new database. Are you sure? (y/N) ").lower() != 'y':
            print("Cancelled")
            return

        try:
            with open('schema.sql', 'r') as f:
                schema = f.read()
        except FileNotFoundError:
            print("Error: Could not find schema.sql file")
            return
        except IOError as e:
            print(f"Error reading schema file: {e}")
            return

        try:
            with sqlite3.connect(self.db_path) as con:
                con.executescript(schema)
                print(f"Successfully initialized database at {self.db_path}")
        except sqlite3.Error as e:
            print(f"Database error: {e}")

    def search_library(self):
        """Search for games in the library by name, console, or condition."""
        try:
            search_term = input('Enter search term: ').strip()
            if not search_term:
                print("Search term required")
                return
        except EOFError:
            print("\nSearch cancelled")
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
                        p.acquisition_date,
                        COALESCE(pc.pricecharting_id, 'Not identified') as pricecharting_id,
                        COALESCE(
                            (
                                SELECT price 
                                FROM pricecharting_prices pp 
                                WHERE pp.pricecharting_id = pc.pricecharting_id 
                                AND pp.condition = p.condition
                                ORDER BY pp.retrieve_time DESC 
                                LIMIT 1
                            ), 
                            NULL
                        ) as current_price
                    FROM physical_games p
                    LEFT JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
                    LEFT JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
                    WHERE p.name LIKE ? 
                    OR p.console LIKE ? 
                    OR p.condition LIKE ?
                    ORDER BY p.name ASC
                """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"))
                
                games = cursor.fetchall()
                
                if not games:
                    print("No games found matching that term.")
                    return

                print(f"\nFound {len(games)} games:")
                for i, (id, name, console, condition, source, price, date, pc_id, current_price) in enumerate(games):
                    purchase_price = f"${float(price):.2f}" if price else "no price"
                    market_price = f"${float(current_price):.2f}" if current_price else "no current price"
                    print(f"\n[{i}] {name} ({console}) - {condition} condition")
                    print(f"    {market_price} (bought for {purchase_price} from {source} on {date})")

                try:
                    choice = input('\nSelect a game to edit (or press Enter to cancel): ').strip()
                    if not choice:
                        return
                        
                    choice = int(choice)
                    if not 0 <= choice < len(games):
                        print("Invalid selection")
                        return
                    
                    # Get the selected game's data
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

                except (ValueError, EOFError):
                    print("\nEdit cancelled")
                    return

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
            command = input('What would you like to do? (Ctrl + D to exit) ')
            if not library.execute_command(command):
                print(f"'{command}' is not a valid command")

        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

if __name__ == '__main__':
    main()
