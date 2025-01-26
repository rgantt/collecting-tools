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
        self._ensure_initialized()

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

    def _is_initialized(self) -> bool:
        """Check if database is initialized by looking for physical_games table."""
        try:
            with self._db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='physical_games'
                """)
                return cursor.fetchone() is not None
        except DatabaseError:
            return False

    def _ensure_initialized(self) -> None:
        """Check if database needs initialization and prompt user if needed."""
        if self._is_initialized():
            return

        print("Database not initialized.")
        if input("Would you like to initialize it now? (y/N) ").lower() == 'y':
            self.init_db()
        else:
            raise DatabaseError("Cannot proceed with uninitialized database")

    def register_commands(self):
        self.register("add", "Add a game to your library", self.add_game)
        self.register("search", "Search library", self.search_library)
        self.register("prices", "Retrieve latest prices", self.retrieve_prices)
        self.register("ids", "Retrieve missing game IDs", self.retrieve_ids)
        self.register("want", "Add a game to the wishlist", self.want_game)
        self.register("wishlist", "View your wishlist", self.view_wishlist)
        self.register("help", "Display available commands", self.display_commands)

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
                    (name, console)
                    VALUES (:title, :console)
                """, asdict(game))
                
                physical_id = cursor.lastrowid

                # Insert purchase details
                cursor.execute("""
                    INSERT INTO purchased_games
                    (physical_game, acquisition_date, source, price, condition)
                    VALUES (?, :date, :source, :price, :condition)
                """, (physical_id, *[asdict(game)[k] for k in ['date', 'source', 'price', 'condition']]))

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

        bar_length = 50
        bar = '-' * bar_length
        
        # Print progress on same line
        print(f"\rProgress: [{bar}] 0% (0/{len(games)})", end='', flush=True)

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
                    percent = (processed / len(games)) * 100
                    filled = int(bar_length * processed // len(games))
                    bar = '=' * filled + '-' * (bar_length - filled)
                    
                    # Print progress on same line
                    print(f"\rProgress: [{bar}] {percent:.1f}% ({processed}/{len(games)})", end='', flush=True)
                    
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
        
        # Show initial progress bar at 0%
        bar_length = 50
        bar = '-' * bar_length
        print(f"\rProgress: [{bar}] 0.0% (0/{len(games)})", end='', flush=True)

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
        try:
            with open('schema/collection.sql', 'r') as f:
                schema = f.read()
        except FileNotFoundError:
            raise DatabaseError("Could not find schema/collection.sql file")
        except IOError as e:
            raise DatabaseError(f"Error reading schema file: {e}")

        try:
            with sqlite3.connect(self.db_path) as con:
                con.executescript(schema)
                print(f"Successfully initialized database at {self.db_path}")
        except sqlite3.Error as e:
            raise DatabaseError(f"Database initialization failed: {e}")

    def want_game(self) -> None:
        """Add a new game to the wishlist interactively."""
        try:
            title = input('Title: ').strip()
            console = input('Console: ').strip()
            
            if not title or not console:
                print("Title and console are required")
                return
            
        except EOFError:
            print("\nInput cancelled")
            return

        try:
            with self._db_connection() as conn:
                cursor = conn.cursor()
                
                # Insert into physical_games
                cursor.execute("""
                    INSERT INTO physical_games
                    (name, console)
                    VALUES (?, ?)
                """, (title, console))
                
                physical_id = cursor.lastrowid

                # Add to wanted_games
                cursor.execute("""
                    INSERT INTO wanted_games
                    (physical_game)
                    VALUES (?)
                """, (physical_id,))

                # Insert into pricecharting_games
                cursor.execute("""
                    INSERT INTO pricecharting_games (name, console)
                    VALUES (?, ?)
                """, (title, console))
                
                pricecharting_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO physical_games_pricecharting_games
                    (physical_game, pricecharting_game)
                    VALUES (?, ?)
                """, (physical_id, pricecharting_id))
                
                print("Game added to wishlist successfully")
                
        except DatabaseError as e:
            print(f"Failed to add game to wishlist: {e}")

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
                # First, let's debug by printing all games in wanted_games
                cursor = con.execute("""
                    SELECT p.name, p.console, w.id 
                    FROM physical_games p
                    JOIN wanted_games w ON p.id = w.physical_game
                """)
                wanted = cursor.fetchall()
                print("\nWanted games in database:")
                for name, console, wid in wanted:
                    print(f"- {name} ({console}) [wanted_id: {wid}]")

                # Now the main search query
                cursor = con.execute("""
                    SELECT 
                        p.id,
                        p.name,
                        p.console,
                        pg.condition,
                        pg.source,
                        pg.price,
                        pg.acquisition_date,
                        COALESCE(pc.pricecharting_id, 'Not identified') as pricecharting_id,
                        COALESCE(
                            (
                                SELECT price 
                                FROM pricecharting_prices pp 
                                WHERE pp.pricecharting_id = pc.pricecharting_id 
                                AND pp.condition = COALESCE(pg.condition, 'complete')
                                ORDER BY pp.retrieve_time DESC 
                                LIMIT 1
                            ), 
                            NULL
                        ) as current_price,
                        CASE WHEN w.id IS NOT NULL THEN 1 ELSE 0 END as wanted
                    FROM physical_games p
                    LEFT JOIN purchased_games pg ON p.id = pg.physical_game
                    LEFT JOIN wanted_games w ON p.id = w.physical_game
                    LEFT JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
                    LEFT JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
                    WHERE LOWER(p.name) LIKE LOWER('%' || ? || '%')
                    OR LOWER(p.console) LIKE LOWER('%' || ? || '%')
                    GROUP BY p.id
                    ORDER BY p.name ASC
                """, (search_term, search_term))
                
                games = cursor.fetchall()
                
                if not games:
                    print("\nNo games found matching that term.")
                    return

                print(f"\nFound {len(games)} games:")
                for i, (id, name, console, condition, source, price, date, pc_id, current_price, wanted) in enumerate(games):
                    try:
                        if wanted:
                            print(f"[{i}] {name} ({console}) - WISHLIST")
                            market_price = f"${float(current_price):.2f}" if current_price else "no current price"
                            print(f"    Current market price: {market_price}")
                        else:
                            purchase_price = f"${float(price):.2f}" if price else "no price"
                            market_price = f"${float(current_price):.2f}" if current_price else "no current price"
                            print(f"[{i}] {name} ({console}) - {condition} condition")
                            print(f"    {market_price} (bought for {purchase_price} from {source} on {date})")
                    except (TypeError, ValueError) as e:
                        if wanted:
                            print(f"[{i}] {name} ({console}) - WISHLIST")
                            print(f"    Current market price: no current price")
                        else:
                            print(f"[{i}] {name} ({console})")
                            print(f"    Error displaying price info: {e}")
                    print()  # Single newline between entries

                choice = input('\nSelect a game to edit (or press Enter to cancel): ').strip()
                if not choice:
                    return
                    
                choice = int(choice)
                if not 0 <= choice < len(games):
                    print("Invalid selection")
                    return
                
                # Get the selected game's data
                game_id = games[choice][0]
                wanted = games[choice][9]  # The 'wanted' flag from our query
                
                # Inside the edit section after selecting a game
                if wanted:  # Add this new section for wishlist items
                    remove = input('Remove from wishlist? (default: No) [y/N]: ').strip().lower()
                    if remove == 'y':
                        cursor.execute("""
                            DELETE FROM wanted_games
                            WHERE physical_game = ?
                        """, (game_id,))
                        print("Game removed from wishlist")
                        return

                print("\nEnter new values (or press Enter to keep current value)")
                
                try:
                    physical_updates = {}
                    purchase_updates = {}
                    
                    name = input(f'Name [{games[choice][1]}]: ').strip()
                    if name:
                        physical_updates['name'] = name
                    
                    console = input(f'Console [{games[choice][2]}]: ').strip()
                    if console:
                        physical_updates['console'] = console
                    
                    if not wanted:  # Only ask for these details if it's not a wishlist item
                        condition = input(f'Condition [{games[choice][3]}]: ').strip()
                        if condition:
                            purchase_updates['condition'] = condition
                        
                        source = input(f'Source [{games[choice][4]}]: ').strip()
                        if source:
                            purchase_updates['source'] = source
                        
                        price = input(f'Price [{games[choice][5]}]: ').strip()
                        if price:
                            purchase_updates['price'] = price
                        
                        date = self._get_valid_date('Date', games[choice][6])
                        if date != games[choice][6]:
                            purchase_updates['acquisition_date'] = date

                    if not physical_updates and not purchase_updates:
                        print("No changes made")
                        return

                    # Update physical_games if needed
                    if physical_updates:
                        set_clause = ", ".join(f"{k} = ?" for k in physical_updates.keys())
                        values = list(physical_updates.values()) + [game_id]
                        cursor.execute(f"""
                            UPDATE physical_games
                            SET {set_clause}
                            WHERE id = ?
                        """, values)

                    # Update purchased_games if needed (only for non-wishlist items)
                    if purchase_updates and not wanted:
                        set_clause = ", ".join(f"{k} = ?" for k in purchase_updates.keys())
                        values = list(purchase_updates.values()) + [game_id]
                        cursor.execute(f"""
                            UPDATE purchased_games
                            SET {set_clause}
                            WHERE physical_game = ?
                        """, values)

                    # Update pricecharting_games if name/console changed
                    if physical_updates.get('name') or physical_updates.get('console'):
                        cursor.execute("""
                            UPDATE pricecharting_games
                            SET name = COALESCE(?, name),
                                console = COALESCE(?, console)
                            WHERE id IN (
                                SELECT pricecharting_game
                                FROM physical_games_pricecharting_games
                                WHERE physical_game = ?
                            )
                        """, (physical_updates.get('name'), physical_updates.get('console'), game_id))

                    print("Changes saved")

                except (ValueError, EOFError):
                    print("\nEdit cancelled")
                    return

        except sqlite3.Error as e:
            print(f"Database error: {e}")

    def view_wishlist(self) -> None:
        """Display all games in the wishlist, optionally filtered by a search term."""
        try:
            search_term = input('Enter search term (or press Enter to show all): ').strip()
        except EOFError:
            print("\nWishlist view cancelled")
            return

        try:
            with self._db_connection() as conn:
                cursor = conn.cursor()
                
                query = """
                    SELECT 
                        p.name,
                        p.console,
                        COALESCE(
                            (
                                SELECT price 
                                FROM pricecharting_prices pp 
                                JOIN physical_games_pricecharting_games pcg ON pp.pricecharting_id = pcg.pricecharting_game
                                WHERE pcg.physical_game = p.id
                                AND pp.condition = 'complete'
                                ORDER BY pp.retrieve_time DESC 
                                LIMIT 1
                            ),
                            NULL
                        ) as current_price
                    FROM physical_games p
                    JOIN wanted_games w ON p.id = w.physical_game
                    WHERE 1=1
                """
                params = []
                
                if search_term:
                    query += " AND (LOWER(p.name) LIKE LOWER(?) OR LOWER(p.console) LIKE LOWER(?))"
                    params.extend([f'%{search_term}%', f'%{search_term}%'])
                
                query += " ORDER BY p.name ASC"
                
                cursor.execute(query, params)
                games = cursor.fetchall()
                
                if not games:
                    if search_term:
                        print(f"\nNo wishlist items found matching '{search_term}'")
                    else:
                        print("\nYour wishlist is empty")
                    return

                print(f"\nWishlist items{' matching ' + search_term if search_term else ''}:")
                for name, console, current_price in games:
                    print(f"\n{name} ({console})")
                    try:
                        price_str = f"${float(current_price):.2f}" if current_price else "no current price"
                    except (TypeError, ValueError):
                        price_str = "no current price"
                    print(f"    Current market price: {price_str}")
                    
        except DatabaseError as e:
            print(f"Failed to retrieve wishlist: {e}")

def main():
    parser = argparse.ArgumentParser(description='Manage your game collection')
    parser.add_argument('-d', '--db', required=True, help='Path to SQLite database')
    args = parser.parse_args()

    library = GameLibrary(args.db)
    
    # Display commands only once at startup
    library.display_commands()
    
    while True:
        try:
            command = input('\nWhat would you like to do? (Ctrl + D to exit) ')
            if not library.execute_command(command):
                print(f"'{command}' is not a valid command")

        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

if __name__ == '__main__':
    main()
