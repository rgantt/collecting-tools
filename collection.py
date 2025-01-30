#!/usr/local/bin/python3

import argparse
import sqlite3
from typing import Callable, List, Optional, Sequence, Iterator, Any, Dict, Tuple
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

@dataclass
class SearchResult:
    id: int
    name: str
    console: str
    condition: Optional[str]
    source: Optional[str]
    price: Optional[str]
    date: Optional[str]
    pricecharting_id: Optional[str]
    current_prices: Dict[str, float]
    is_wanted: bool

@dataclass
class ValueStats:
    total_purchase: float
    total_market: float
    top_valuable: List[Tuple[str, str, str, float, float]]  # (name, console, condition, purchase, current)
    biggest_changes: List[Tuple[str, str, str, float, float, float, float]]  # (name, console, condition, old, new, change, pct)

@dataclass
class GameAdditionResult:
    success: bool
    message: str
    game_id: Optional[int] = None

@dataclass
class ConsoleDistribution:
    console: str
    game_count: int
    percentage: float
    most_expensive_game: Optional[str]
    most_expensive_condition: Optional[str]
    most_expensive_price: Optional[float]

@dataclass
class RecentAddition:
    name: str
    console: str
    condition: Optional[str]
    source: Optional[str]
    price: Optional[float]
    date: str
    current_prices: Dict[str, float]
    is_wanted: bool

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
        self.register("value", "Display collection value statistics", self.display_value_stats)
        self.register("distribution", "Display collection distribution by console", self.display_distribution)
        self.register("recent", "Display recently added games", self.display_recent)
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
        while True:
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

            try:
                id_data = get_game_id(-1, game.title, game.console) if game.title and game.console else None
                break
            except ValueError as err:
                print(f"\nWarning: Could not retrieve price tracking ID: {err}")
                choice = input("Would you like to (e)dit the game info, or (c)ontinue without price tracking? [e/c]: ").lower()
                if choice == 'c':
                    id_data = None
                    break
                elif choice == 'e':
                    previous_game = game
                    continue
                else:
                    print("Invalid choice, cancelling game addition")
                    return

            with self._db_connection() as conn:
                result = self.add_game_to_database(conn, game, id_data)
                print(result.message)

    def retrieve_prices(self):
        try:
            # First get total count of eligible games
            with self._db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(DISTINCT pricecharting_id)
                    FROM latest_prices
                    WHERE retrieve_time < datetime('now', '-7 days')
                    OR retrieve_time IS NULL
                    ORDER BY name ASC
                """)
                total_eligible = cursor.fetchone()[0]
            
            print(f"\nFound {total_eligible} games eligible for price updates")
            
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
        previous_game = None
        while True:  # Loop to allow retrying if ID retrieval fails
            try:
                title = input(f'Title{f" [{previous_game[0]}]" if previous_game else ""}: ').strip() or (previous_game[0] if previous_game else "")
                console = input(f'Console{f" [{previous_game[1]}]" if previous_game else ""}: ').strip() or (previous_game[1] if previous_game else "")
                
                if not title or not console:
                    print("Title and console are required")
                    return
                
            except EOFError:
                print("\nInput cancelled")
                return

            # Try to retrieve the pricecharting ID before adding to database
            try:
                # Using -1 as temporary ID since the game isn't in DB yet
                id_data = get_game_id(-1, title, console)
                break  # If successful, exit the loop and proceed with adding the game
            except ValueError as err:
                print(f"\nWarning: Could not retrieve price tracking ID: {err}")
                choice = input("Would you like to (e)dit the game info, or (c)ontinue without price tracking? [e/c]: ").lower()
                if choice == 'c':
                    id_data = None
                    break
                elif choice == 'e':
                    print("\nPlease enter the game information again:")
                    previous_game = (title, console)  # Store the current game data for the next iteration
                    continue
                else:
                    print("Invalid choice, cancelling game addition")
                    return

        # Move this try block outside the while loop and fix indentation
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
                    
                    print("Game added to wishlist successfully with price tracking enabled")
                else:
                    print("Game added to wishlist successfully without price tracking")
                
        except DatabaseError as e:
            print(f"Failed to add game to wishlist: {e}")

    def search_library(self):
        """Interactive search interface for the library."""
        try:
            search_term = input('Enter search term: ').strip()
            if not search_term:
                print("Search term required")
                return
        except EOFError:
            print("\nSearch cancelled")
            return

        try:
            with self._db_connection() as conn:
                results = search_games(conn, search_term)
                
                if not results:
                    print("\nNo games found matching that term.")
                    return

                print(f"\nFound {len(results)} games:")
                for i, result in enumerate(results):
                    if result.is_wanted:
                        print(f"[{i}] {result.name} ({result.console}) - WISHLIST")
                        prices = []
                        for condition, price in result.current_prices.items():
                            if price:
                                prices.append(f"{condition}: ${price:.2f}")
                        market_prices = " | ".join(prices) if prices else "no current prices"
                        print(f"    {market_prices}")
                    else:
                        purchase_price = f"${float(result.price):.2f}" if result.price else "no price"
                        current_price = None
                        if result.condition:
                            current_price = result.current_prices.get(result.condition.lower())
                        
                        market_price = f"{result.condition}: ${current_price:.2f}" if current_price else "no current price"
                        print(f"[{i}] {result.name} ({result.console})")
                        print(f"    {market_price} (bought for {purchase_price} from {result.source} on {result.date})")
                    print()

                # Handle game selection and editing...
                # (The edit functionality would be refactored similarly)

        except DatabaseError as e:
            print(f"Search failed: {e}")

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

    def display_value_stats(self):
        """Display collection value statistics."""
        try:
            with self._db_connection() as conn:
                stats = get_collection_value_stats(conn)
                
                print("\nCollection Value Statistics")
                print("==========================")
                print(f"Total Purchase Value: ${stats.total_purchase:.2f}")
                print(f"Total Market Value:   ${stats.total_market:.2f}")
                
                if stats.total_purchase > 0:
                    roi = ((stats.total_market - stats.total_purchase) / stats.total_purchase) * 100
                    print(f"Overall ROI:         {roi:+.1f}%")

                if stats.top_valuable:
                    print("\nTop 5 Most Valuable Games")
                    print("=======================")
                    for name, console, condition, purchase, current in stats.top_valuable:
                        print(f"{name} ({console}) - {condition}")
                        print(f"  Current: ${current:.2f}" + (f" (bought: ${purchase:.2f})" if purchase else ""))

                if stats.biggest_changes:
                    print("\nBiggest Price Changes (Last 3 Months)")
                    print("===================================")
                    for name, console, condition, old, new, change, pct in stats.biggest_changes:
                        print(f"{name} ({console}) - {condition}")
                        print(f"  ${old:.2f} → ${new:.2f} ({pct:+.1f}%)")

        except DatabaseError as e:
            print(f"Failed to retrieve collection statistics: {e}")

    def display_distribution(self) -> None:
        """Display distribution of games across consoles."""
        try:
            with self._db_connection() as conn:
                distributions = get_console_distribution(conn)
                
                if not distributions:
                    print("\nNo games in collection.")
                    return
                
                total_games = sum(d.game_count for d in distributions)
                print(f"\nTotal Games in Collection: {total_games}")
                print("\nDistribution by Console")
                print("======================")
                
                # Calculate column widths
                console_width = max(len("Console"), max(len(d.console) for d in distributions))
                count_width = max(len("Count"), max(len(str(d.game_count)) for d in distributions))
                percent_width = max(len("Percent"), max(len(f"{d.percentage}%") for d in distributions))
                
                # Print header
                header = (
                    f"{'Console':<{console_width}} | "
                    f"{'Count':>{count_width}} | "
                    f"{'Percent':>{percent_width}} | "
                    f"Most Expensive Game"
                )
                print(header)
                print("-" * len(header))
                
                # Print each row
                for dist in distributions:
                    most_expensive = (
                        f"{dist.most_expensive_game} ({dist.most_expensive_condition}): "
                        f"${dist.most_expensive_price:.2f}"
                        if dist.most_expensive_game and dist.most_expensive_price
                        else "No price data"
                    )
                    print(
                        f"{dist.console:<{console_width}} | "
                        f"{dist.game_count:>{count_width}} | "
                        f"{dist.percentage:>{percent_width-1}}% | "
                        f"{most_expensive}"
                    )

        except DatabaseError as e:
            print(f"Failed to retrieve collection distribution: {e}")

    def display_recent(self) -> None:
        """Display recently added games."""
        try:
            with self._db_connection() as conn:
                recent = get_recent_additions(conn)
                
                if not recent:
                    print("\nNo games found.")
                    return

                print("\nRecently Added Games")
                print("===================")
                
                for addition in recent:
                    if addition.is_wanted:
                        print(f"\n{addition.name} ({addition.console}) - WISHLIST")
                        prices = []
                        for condition, price in addition.current_prices.items():
                            if price:
                                prices.append(f"{condition}: ${price:.2f}")
                        market_prices = " | ".join(prices) if prices else "no current prices"
                        print(f"    {market_prices}")
                    else:
                        purchase_str = f"${addition.price:.2f}" if addition.price else "no price"
                        current_price = None
                        if addition.condition:
                            current_price = addition.current_prices.get(addition.condition.lower())
                        
                        market_price = (
                            f"{addition.condition}: ${current_price:.2f}" 
                            if current_price else "no current price"
                        )
                        print(f"\n{addition.name} ({addition.console})")
                        print(
                            f"    {market_price} (bought for {purchase_str} "
                            f"from {addition.source} on {addition.date})"
                        )

        except DatabaseError as e:
            print(f"Failed to retrieve recent additions: {e}")

def search_games(
    conn: sqlite3.Connection,
    search_term: str
) -> List[SearchResult]:
    """Search for games in the database matching the search term."""
    cursor = conn.cursor()
    
    cursor.execute("""
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
        WHERE LOWER(p.name) LIKE LOWER(?) OR LOWER(p.console) LIKE LOWER(?)
        GROUP BY p.id
        ORDER BY p.name ASC
    """, (f'%{search_term}%', f'%{search_term}%'))
    
    results = []
    for row in cursor.fetchall():
        current_prices = {
            'complete': float(row[8]) if row[8] else None,
            'loose': float(row[9]) if row[9] else None,
            'new': float(row[10]) if row[10] else None
        }
        
        results.append(SearchResult(
            id=row[0],
            name=row[1],
            console=row[2],
            condition=row[3],
            source=row[4],
            price=row[5],
            date=row[6],
            pricecharting_id=row[7],
            current_prices=current_prices,
            is_wanted=bool(row[11])
        ))
    
    return results

def get_collection_value_stats(conn: sqlite3.Connection) -> ValueStats:
    """Get various statistics about collection value."""
    cursor = conn.cursor()
    
    # Get total purchase value
    cursor.execute("""
        SELECT COALESCE(SUM(CAST(price AS DECIMAL)), 0) as total_purchase
        FROM purchased_games
    """)
    total_purchase = cursor.fetchone()[0]

    # Get current market value
    cursor.execute("""
        WITH latest_prices AS (
            SELECT 
                pricecharting_id,
                condition,
                price,
                ROW_NUMBER() OVER (PARTITION BY pricecharting_id, condition ORDER BY retrieve_time DESC) as rn
            FROM pricecharting_prices
        )
        SELECT COALESCE(SUM(CAST(lp.price AS DECIMAL)), 0) as total_market
        FROM purchased_games pg
        JOIN physical_games p ON pg.physical_game = p.id
        JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
        JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
        LEFT JOIN latest_prices lp ON pc.pricecharting_id = lp.pricecharting_id 
            AND LOWER(pg.condition) = LOWER(lp.condition)
            AND lp.rn = 1
    """)
    total_market = cursor.fetchone()[0]

    # Get top 5 most valuable games
    cursor.execute("""
        WITH latest_prices AS (
            SELECT 
                pricecharting_id,
                condition,
                price,
                ROW_NUMBER() OVER (PARTITION BY pricecharting_id, condition ORDER BY retrieve_time DESC) as rn
            FROM pricecharting_prices
        )
        SELECT 
            p.name,
            p.console,
            pg.condition,
            CAST(pg.price AS DECIMAL) as purchase_price,
            CAST(lp.price AS DECIMAL) as current_price
        FROM purchased_games pg
        JOIN physical_games p ON pg.physical_game = p.id
        JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
        JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
        LEFT JOIN latest_prices lp ON pc.pricecharting_id = lp.pricecharting_id 
            AND LOWER(pg.condition) = LOWER(lp.condition)
            AND lp.rn = 1
        WHERE lp.price IS NOT NULL
        ORDER BY CAST(lp.price AS DECIMAL) DESC
        LIMIT 5
    """)
    top_valuable = cursor.fetchall()

    # Get biggest price changes
    cursor.execute("""
        WITH latest_prices AS (
            SELECT 
                pricecharting_id,
                condition,
                price,
                retrieve_time,
                ROW_NUMBER() OVER (PARTITION BY pricecharting_id, condition ORDER BY retrieve_time DESC) as rn
            FROM pricecharting_prices
            WHERE retrieve_time >= date('now', '-3 months')
        ),
        oldest_prices AS (
            SELECT 
                pricecharting_id,
                condition,
                price,
                retrieve_time,
                ROW_NUMBER() OVER (PARTITION BY pricecharting_id, condition ORDER BY retrieve_time ASC) as rn
            FROM pricecharting_prices
            WHERE retrieve_time >= date('now', '-3 months')
        )
        SELECT 
            p.name,
            p.console,
            pg.condition,
            CAST(op.price AS DECIMAL) as old_price,
            CAST(lp.price AS DECIMAL) as new_price,
            CAST(lp.price AS DECIMAL) - CAST(op.price AS DECIMAL) as price_change,
            ROUND(((CAST(lp.price AS DECIMAL) - CAST(op.price AS DECIMAL)) / CAST(op.price AS DECIMAL) * 100), 2) as percent_change
        FROM purchased_games pg
        JOIN physical_games p ON pg.physical_game = p.id
        JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
        JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
        JOIN latest_prices lp ON pc.pricecharting_id = lp.pricecharting_id 
            AND LOWER(pg.condition) = LOWER(lp.condition)
            AND lp.rn = 1
        JOIN oldest_prices op ON pc.pricecharting_id = op.pricecharting_id 
            AND LOWER(pg.condition) = LOWER(op.condition)
            AND op.rn = 1
        WHERE op.price != lp.price
        ORDER BY ABS(CAST(lp.price AS DECIMAL) - CAST(op.price AS DECIMAL)) DESC
        LIMIT 10
    """)
    biggest_changes = cursor.fetchall()

    return ValueStats(
        total_purchase=float(total_purchase),
        total_market=float(total_market),
        top_valuable=top_valuable,
        biggest_changes=biggest_changes
    )

def get_console_distribution(conn: sqlite3.Connection) -> List[ConsoleDistribution]:
    """Get distribution of games across consoles with most expensive games."""
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH latest_prices AS (
            SELECT 
                pricecharting_id,
                condition,
                price,
                ROW_NUMBER() OVER (PARTITION BY pricecharting_id, condition ORDER BY retrieve_time DESC) as rn
            FROM pricecharting_prices
        ),
        console_games AS (
            SELECT 
                p.console,
                COUNT(*) as game_count,
                ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) as percentage
            FROM physical_games p
            JOIN purchased_games pg ON p.id = pg.physical_game
            GROUP BY p.console
        ),
        most_expensive AS (
            SELECT 
                p.console,
                p.name,
                pg.condition,
                CAST(lp.price AS DECIMAL) as current_price,
                ROW_NUMBER() OVER (PARTITION BY p.console ORDER BY CAST(lp.price AS DECIMAL) DESC) as rn
            FROM physical_games p
            JOIN purchased_games pg ON p.id = pg.physical_game
            JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
            JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
            JOIN latest_prices lp ON pc.pricecharting_id = lp.pricecharting_id 
                AND LOWER(pg.condition) = LOWER(lp.condition)
                AND lp.rn = 1
        )
        SELECT 
            cg.console,
            cg.game_count,
            cg.percentage,
            me.name,
            me.condition,
            me.current_price
        FROM console_games cg
        LEFT JOIN most_expensive me ON cg.console = me.console AND me.rn = 1
        ORDER BY cg.game_count DESC, cg.console
    """)
    
    return [
        ConsoleDistribution(
            console=row[0],
            game_count=row[1],
            percentage=row[2],
            most_expensive_game=row[3],
            most_expensive_condition=row[4],
            most_expensive_price=float(row[5]) if row[5] else None
        )
        for row in cursor.fetchall()
    ]

def get_recent_additions(conn: sqlite3.Connection, limit: int = 10) -> List[RecentAddition]:
    """Get recently added games to both collection and wishlist."""
    cursor = conn.cursor()
    
    cursor.execute("""
        WITH latest_prices AS (
            SELECT 
                pricecharting_id,
                condition,
                price,
                ROW_NUMBER() OVER (PARTITION BY pricecharting_id, condition ORDER BY retrieve_time DESC) as rn
            FROM pricecharting_prices
        )
        SELECT 
            p.name,
            p.console,
            pg.condition,
            pg.source,
            CAST(pg.price AS DECIMAL) as purchase_price,
            pg.acquisition_date,
            COALESCE(
                (
                    SELECT price 
                    FROM latest_prices lp
                    WHERE lp.pricecharting_id = pc.pricecharting_id 
                    AND lp.condition = 'complete'
                    AND lp.rn = 1
                ), 
                NULL
            ) as price_complete,
            COALESCE(
                (
                    SELECT price 
                    FROM latest_prices lp
                    WHERE lp.pricecharting_id = pc.pricecharting_id 
                    AND lp.condition = 'loose'
                    AND lp.rn = 1
                ), 
                NULL
            ) as price_loose,
            COALESCE(
                (
                    SELECT price 
                    FROM latest_prices lp
                    WHERE lp.pricecharting_id = pc.pricecharting_id 
                    AND lp.condition = 'new'
                    AND lp.rn = 1
                ), 
                NULL
            ) as price_new,
            CASE WHEN w.id IS NOT NULL THEN 1 ELSE 0 END as wanted
        FROM physical_games p
        LEFT JOIN purchased_games pg ON p.id = pg.physical_game
        LEFT JOIN wanted_games w ON p.id = w.physical_game
        LEFT JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
        LEFT JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
        ORDER BY COALESCE(pg.acquisition_date, w.id) DESC
        LIMIT ?
    """, (limit,))
    
    return [
        RecentAddition(
            name=row[0],
            console=row[1],
            condition=row[2],
            source=row[3],
            price=float(row[4]) if row[4] else None,
            date=row[5],
            current_prices={
                'complete': float(row[6]) if row[6] else None,
                'loose': float(row[7]) if row[7] else None,
                'new': float(row[8]) if row[8] else None
            },
            is_wanted=bool(row[9])
        )
        for row in cursor.fetchall()
    ]

def add_game_to_database(
    conn: sqlite3.Connection,
    game: GameData,
    id_data: Optional[dict] = None
) -> GameAdditionResult:
    """
    Add a game to the database with optional price tracking ID.
    Pure function that handles the database operations without I/O.
    """
    try:
        cursor = conn.cursor()
        
        # Insert into physical_games
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

        if id_data:
            # Check for existing pricecharting ID
            cursor.execute("""
                SELECT id FROM pricecharting_games 
                WHERE pricecharting_id = ?
            """, (id_data['pricecharting_id'],))
            
            existing_pc_game = cursor.fetchone()
            
            if existing_pc_game:
                pricecharting_id = existing_pc_game[0]
            else:
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
            
            return GameAdditionResult(True, "Game added successfully with price tracking enabled", physical_id)
        
        return GameAdditionResult(True, "Game added successfully without price tracking", physical_id)

    except sqlite3.Error as e:
        return GameAdditionResult(False, f"Database error: {e}")

def add_game_to_wishlist(
    conn: sqlite3.Connection,
    title: str,
    console: str,
    id_data: Optional[dict] = None
) -> GameAdditionResult:
    """
    Add a game to the wishlist with optional price tracking ID.
    Pure function that handles the database operations without I/O.
    """
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO physical_games
            (name, console)
            VALUES (?, ?)
        """, (title, console))
        
        physical_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO wanted_games
            (physical_game)
            VALUES (?)
        """, (physical_id,))

        if id_data:
            cursor.execute("""
                SELECT id FROM pricecharting_games 
                WHERE pricecharting_id = ?
            """, (id_data['pricecharting_id'],))
            
            existing_pc_game = cursor.fetchone()
            
            if existing_pc_game:
                pricecharting_id = existing_pc_game[0]
            else:
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
            
            return GameAdditionResult(True, "Game added to wishlist with price tracking enabled", physical_id)
        
        return GameAdditionResult(True, "Game added to wishlist without price tracking", physical_id)

    except sqlite3.Error as e:
        return GameAdditionResult(False, f"Database error: {e}")

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
