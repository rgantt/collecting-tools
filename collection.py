#!/usr/local/bin/python3

import argparse
import sqlite3
from typing import Callable, List, Optional, Sequence, Iterator, Any
import json
from lib.price_retrieval import retrieve_games as retrieve_games_for_prices
from lib.price_retrieval import get_game_prices, insert_price_records
from lib.id_retrieval import retrieve_games as retrieve_games_for_ids
from lib.id_retrieval import get_game_id, insert_game_ids
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from contextlib import contextmanager

@dataclass
class GameData:
    title: str
    console: str
    condition: str
    source: str
    price: str
    date: str

class GameLibraryError(Exception):
    """Base exception for GameLibrary errors."""
    pass

class DatabaseError(GameLibraryError):
    """Raised when database operations fail."""
    pass

class GameLibrary:
    def __init__(self, db_path: str | Path):
        """Initialize GameLibrary with database path."""
        self.db_path = Path(db_path)
        self._commands: list[tuple[str, str, Callable[[], None]]] = []
        self.register_commands()

    @contextmanager
    def _db_connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        try:
            conn = sqlite3.connect(self.db_path)
            yield conn
            conn.commit()
        except sqlite3.Error as e:
            raise DatabaseError(f"Database operation failed: {e}")
        finally:
            conn.close()

    def _get_valid_date(self, prompt: str, current_value: Optional[str] = None) -> str:
        """Get a valid ISO-8601 date from user input."""
        while True:
            try:
                date_input = input(f"{prompt} [{current_value or ''}]: ").strip()
                
                if current_value and not date_input:
                    return current_value
                
                if not date_input:
                    print("Date is required. Format: YYYY-MM-DD")
                    continue
                
                # Validate by attempting to parse
                datetime.strptime(date_input, '%Y-%m-%d')
                return date_input
            
            except ValueError:
                print("Invalid date format. Please use YYYY-MM-DD (e.g., 2024-03-15)")
            except EOFError:
                raise

    def register_commands(self):
        self.register("add", "Add a game to your library", self.add_game)
        self.register("search", "Search library", self.search_library)
        self.register("prices", "Retrieve latest prices", self.retrieve_prices)
        self.register("ids", "Retrieve missing game IDs", self.retrieve_ids)
        self.register("init", "Initialize new database", self.init_db)

    def register(self, command: str, description: str, func: Callable[[], None]):
        self._commands.append((command, description, func))

    def display_commands(self):
        print("\nAvailable commands:")
        for command, desc, _ in self._commands:
            print(f"{command:8} - {desc}")
        print()

    def execute_command(self, command: str) -> bool:
        command = command.lower().strip()
        for cmd, _, func in self._commands:
            if cmd == command:
                func()
                return True
        return False

    def add_game(self) -> None:
        """Add a new game to the library interactively."""
        try:
            game = GameData(
                title=input('Title: ').strip(),
                console=input('Console: ').strip(),
                condition=input('Condition: ').strip(),
                source=input('Source: ').strip(),
                price=input('Price: ').strip(),
                date=self._get_valid_date('Date')
            )
        except EOFError:
            print("\nInput cancelled")
            return

        try:
            with self._db_connection() as conn:
                cursor = conn.cursor()
                
                # Using a transaction to ensure data consistency
                cursor.execute("""
                    INSERT INTO physical_games
                    (acquisition_date, source, price, name, console, condition)
                    VALUES (:date, :source, :price, :title, :console, :condition)
                """, asdict(game))
                
                physical_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO pricecharting_games (name, console)
                    VALUES (:title, :console)
                """, asdict(game))
                
                pricecharting_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO physical_games_pricecharting_games
                    (physical_game, pricecharting_game)
                    VALUES (?, ?)
                """, (physical_id, pricecharting_id))
                
                print("Game added successfully")
                
        except DatabaseError as e:
            print(f"Failed to add game: {e}")

    def retrieve_prices(self) -> None:
        """Retrieve and update prices for games in the library."""
        try:
            max_prices = input('Maximum prices to retrieve (optional): ').strip()
            max_prices = int(max_prices) if max_prices else None
        except ValueError:
            print("Invalid number entered")
            return
        except EOFError:
            print("\nOperation cancelled")
            return

        games = retrieve_games_for_prices(self.db_path, max_prices)
        if not games:
            print("No games found needing price updates.")
            return

        print(f"Retrieving prices for {len(games)} games...")
        
        # Use list comprehension for collecting results
        results = [
            (game, get_game_prices(game))
            for game in games
        ]
        
        successful = [(game, prices) for game, prices in results if prices]
        failed = [(game, str(prices)) for game, prices in results if isinstance(prices, Exception)]

        if successful:
            try:
                with self._db_connection() as conn:
                    insert_price_records([price for _, price in successful], conn)
                print(f"Updated prices for {len(successful)} games")
            except DatabaseError as e:
                print(f"Failed to save prices: {e}")

        if failed:
            print("\nFailures:")
            for game, error in failed:
                print(f"- {game['name']}: {error}")

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
    parser = argparse.ArgumentParser(description='Manage your game collection')
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
