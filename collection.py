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
        previous_game = None
        while True:  # Loop to allow retrying if ID retrieval fails
            try:
                game = GameData(
                    title=input(f'Title{f" [{previous_game.title}]" if previous_game else ""}: ').strip() or (previous_game.title if previous_game else ""),
                    console=input(f'Console{f" [{previous_game.console}]" if previous_game else ""}: ').strip() or (previous_game.console if previous_game else ""),
                    condition=input(f'Condition{f" [{previous_game.condition}]" if previous_game else ""}: ').strip() or (previous_game.condition if previous_game else ""),
                    source=input(f'Source{f" [{previous_game.source}]" if previous_game else ""}: ').strip() or (previous_game.source if previous_game else ""),
                    price=input(f'Price{f" [{previous_game.price}]" if previous_game else ""}: ').strip() or (previous_game.price if previous_game else ""),
                    date=self._get_valid_date('Date', previous_game.date if previous_game else None)
                )
            except EOFError:
                print("\nInput cancelled")
                return

            # Try to retrieve the pricecharting ID before adding to database
            try:
                # Using -1 as temporary ID since the game isn't in DB yet
                id_data = get_game_id(-1, game.title, game.console)
                break  # If successful, exit the loop and proceed with adding the game
            except ValueError as err:
                print(f"\nWarning: Could not retrieve price tracking ID: {err}")
                choice = input("Would you like to (e)dit the game info, or (c)ontinue without price tracking? [e/c]: ").lower()
                if choice == 'c':
                    id_data = None
                    break
                elif choice == 'e':
                    print("\nPlease enter the game information again:")
                    previous_game = game  # Store the current game data for the next iteration
                    continue
                else:
                    print("Invalid choice, cancelling game addition")
                    return

        try:
            with self._db_connection() as conn:
                cursor = conn.cursor()
                
                # Using a transaction to ensure data consistency
                cursor.execute("""
                    INSERT INTO physical_games
                    (name, console)
                    VALUES (?, ?)
                """, (game.title, game.console))
                
                physical_id = cursor.lastrowid

                # Insert purchase details
                cursor.execute("""
                    INSERT INTO purchased_games
                    (physical_game, acquisition_date, source, price, condition)
                    VALUES (?, ?, ?, ?, ?)
                """, (physical_id, game.date, game.source, game.price, game.condition))

                # Only add pricecharting info if we successfully retrieved an ID
                if id_data:
                    # First check if we already have this pricecharting ID in our database
                    cursor.execute("""
                        SELECT id FROM pricecharting_games 
                        WHERE pricecharting_id = ?
                    """, (id_data['pricecharting_id'],))
                    
                    existing_pc_game = cursor.fetchone()
                    
                    if existing_pc_game:
                        # If we already have this game in pricecharting_games, just link to it
                        pricecharting_id = existing_pc_game[0]
                    else:
                        # Otherwise create a new pricecharting_games entry
                        cursor.execute("""
                            INSERT INTO pricecharting_games (name, console, pricecharting_id)
                            VALUES (?, ?, ?)
                        """, (id_data['name'], id_data['console'], id_data['pricecharting_id']))
                        pricecharting_id = cursor.lastrowid

                    cursor.execute("""
                        INSERT INTO physical_games_pricecharting_games
                        (physical_game, pricecharting_game)
                        VALUES (?, ?)
                    """, (physical_id, pricecharting_id))
                    
                    print("Game added successfully with price tracking enabled")
                else:
                    print("Game added successfully without price tracking")
                
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
                                AND pp.condition = 'complete'
                                ORDER BY pp.retrieve_time DESC 
                                LIMIT 1
                            ), 
                            NULL
                        ) as current_price_complete,
                        COALESCE(
                            (
                                SELECT price 
                                FROM pricecharting_prices pp 
                                WHERE pp.pricecharting_id = pc.pricecharting_id 
                                AND pp.condition = 'loose'
                                ORDER BY pp.retrieve_time DESC 
                                LIMIT 1
                            ), 
                            NULL
                        ) as current_price_loose,
                        COALESCE(
                            (
                                SELECT price 
                                FROM pricecharting_prices pp 
                                WHERE pp.pricecharting_id = pc.pricecharting_id 
                                AND pp.condition = 'new'
                                ORDER BY pp.retrieve_time DESC 
                                LIMIT 1
                            ), 
                            NULL
                        ) as current_price_new,
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
                for i, (id, name, console, condition, source, price, date, pc_id, price_complete, price_loose, price_new, wanted) in enumerate(games):
                    try:
                        if wanted:
                            print(f"[{i}] {name} ({console}) - WISHLIST")
                            prices = []
                            if price_loose:
                                prices.append(f"loose: ${float(price_loose):.2f}")
                            if price_complete:
                                prices.append(f"complete: ${float(price_complete):.2f}")
                            if price_new:
                                prices.append(f"new: ${float(price_new):.2f}")
                            market_prices = " | ".join(prices) if prices else "no current prices"
                            print(f"    {market_prices}")
                        else:
                            purchase_price = f"${float(price):.2f}" if price else "no price"
                            market_price = f"{condition}: ${float(price_complete):.2f}" if price_complete else "no current price"
                            print(f"[{i}] {name} ({console})")
                            print(f"    {market_price} (bought for {purchase_price} from {source} on {date})")
                    except (TypeError, ValueError) as e:
                        if wanted:
                            print(f"[{i}] {name} ({console}) - WISHLIST")
                            print(f"    Current market prices: no current prices")
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
                        p.id,
                        p.name,
                        p.console,
                        pc.pricecharting_id,
                        (
                            SELECT price 
                            FROM pricecharting_prices pp 
                            WHERE pp.pricecharting_id = pc.pricecharting_id 
                            AND pp.condition = 'complete'
                            ORDER BY pp.retrieve_time DESC 
                            LIMIT 1
                        ) as price_complete,
                        (
                            SELECT price 
                            FROM pricecharting_prices pp 
                            WHERE pp.pricecharting_id = pc.pricecharting_id 
                            AND pp.condition = 'loose'
                            ORDER BY pp.retrieve_time DESC 
                            LIMIT 1
                        ) as price_loose,
                        (
                            SELECT price 
                            FROM pricecharting_prices pp 
                            WHERE pp.pricecharting_id = pc.pricecharting_id 
                            AND pp.condition = 'new'
                            ORDER BY pp.retrieve_time DESC 
                            LIMIT 1
                        ) as price_new
                    FROM physical_games p
                    JOIN wanted_games w ON p.id = w.physical_game
                    LEFT JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
                    LEFT JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
                    WHERE 1=1
                """
                
                if search_term:
                    query += " AND (LOWER(p.name) LIKE LOWER(?) OR LOWER(p.console) LIKE LOWER(?))"
                    params = [f'%{search_term}%', f'%{search_term}%']
                else:
                    params = []
                
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
                for i, (id, name, console, pc_id, price_complete, price_loose, price_new) in enumerate(games):
                    print(f"\n[{i}] {name} ({console})")
                    try:
                        prices = []
                        if price_loose:
                            prices.append(f"loose: ${float(price_loose):.2f}")
                        if price_complete:
                            prices.append(f"complete: ${float(price_complete):.2f}")
                        if price_new:
                            prices.append(f"new: ${float(price_new):.2f}")
                        price_str = " | ".join(prices) if prices else "no current prices"
                        print(f"    {price_str}")
                    except (TypeError, ValueError):
                        print(f"    no current prices")

                choice = input('\nSelect a game to edit (or press Enter to cancel): ').strip()
                if not choice:
                    return
                    
                try:
                    choice = int(choice)
                    if not 0 <= choice < len(games):
                        print("Invalid selection")
                        return
                except ValueError:
                    print("Invalid selection")
                    return
                
                # Get the selected game's data
                game_id = games[choice][0]
                
                # Offer to remove from wishlist
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
                    
                    name = input(f'Name [{games[choice][1]}]: ').strip()
                    if name:
                        physical_updates['name'] = name
                    
                    console = input(f'Console [{games[choice][2]}]: ').strip()
                    if console:
                        physical_updates['console'] = console

                    if not physical_updates:
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
