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
from lib.collection_utils import (
    GameData, SearchResult, ValueStats, GameAdditionResult, ConsoleDistribution,
    RecentAddition, search_games, get_collection_value_stats, get_console_distribution,
    get_recent_additions, add_game_to_database, add_game_to_wishlist, get_wishlist_items,
    remove_from_wishlist, update_wishlist_item
)

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
            result = add_game_to_database(conn, game, id_data)
            print(result.message)

    def retrieve_prices(self):
        try:
            # First get total count of eligible games
            with self._db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(DISTINCT pricecharting_id)
                    FROM eligible_price_updates
                """)
                total_eligible = cursor.fetchone()[0]
                
                print(f"\nFound {total_eligible} games eligible for price updates\n")
            
                max_prices = input('Maximum prices to retrieve (optional): ')
                max_prices = int(max_prices) if max_prices else None
                
                games = retrieve_games_for_prices(conn, max_prices)
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
                    
                    if successful:
                        try:
                            insert_price_records(successful, conn)
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
        except (ValueError, EOFError):
            print("\nInvalid input")
            return

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
                condition = input('Condition [complete]: ').strip() or 'complete'
                
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

        try:
            with self._db_connection() as conn:
                result = add_game_to_wishlist(conn, title, console, id_data, condition)
                print(result.message)
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

                print(f"\nFound {len(results)} games:\n")
                for i, result in enumerate(results):
                    # Show status indicator and game name
                    status = "" if result.is_wanted else ""
                    print(f"[{i}] {status} {result.name} ({result.console})")

                    # Get current price based on condition
                    condition = result.condition.lower() if result.condition else 'complete'
                    current_price = result.current_prices.get(condition)
                    
                    # Show current price and value change
                    if current_price:
                        print(f"    {condition}: ${current_price:.2f}", end="")
                        if not result.is_wanted and result.price:
                            value_change = current_price - float(result.price)
                            value_change_pct = (value_change / float(result.price)) * 100
                            print(f" ({value_change_pct:+.1f}%)", end="")
                        print()
                    else:
                        print("    no current price")
                    print()

                # Add interactive selection
                try:
                    selection = input("\nSelect a game by number or press Enter to cancel: ").strip()
                    if selection:
                        try:
                            index = int(selection)
                            if 0 <= index < len(results):
                                selected_game = results[index]
                                while True:
                                    print("\nOptions:")
                                    print("1. Delete game")
                                    print("2. Update game")
                                    print("3. Cancel")
                                    
                                    choice = input("\nChoose an option (1-3): ").strip()
                                    
                                    if choice == "1":
                                        confirm = input("Are you sure you want to delete this game? (y/N): ").strip().lower()
                                        if confirm == 'y':
                                            cursor = conn.cursor()
                                            # Delete from purchased_games or wanted_games first
                                            if selected_game.is_wanted:
                                                cursor.execute("DELETE FROM wanted_games WHERE physical_game = ?", (selected_game.id,))
                                            else:
                                                cursor.execute("DELETE FROM purchased_games WHERE physical_game = ?", (selected_game.id,))
                                            
                                            # Delete from physical_games_pricecharting_games if exists
                                            cursor.execute("DELETE FROM physical_games_pricecharting_games WHERE physical_game = ?", (selected_game.id,))
                                            
                                            # Finally delete from physical_games
                                            cursor.execute("DELETE FROM physical_games WHERE id = ?", (selected_game.id,))
                                            
                                            print("Game deleted.")
                                        break
                                    elif choice == "2":
                                        if selected_game.is_wanted:
                                            # Handle wishlist item updates
                                            print("\nEnter new values (or press Enter to keep current value)")
                                            try:
                                                updates = {}
                                                
                                                name = input(f'Name [{selected_game.name}]: ').strip()
                                                if name:
                                                    updates['name'] = name
                                                
                                                console = input(f'Console [{selected_game.console}]: ').strip()
                                                if console:
                                                    updates['console'] = console

                                                if not updates:
                                                    print("No changes made")
                                                else:
                                                    update_wishlist_item(conn, selected_game.id, updates)
                                                    print("Changes saved")
                                            except (ValueError, EOFError):
                                                print("\nEdit cancelled")
                                        else:
                                            # Handle purchased game updates
                                            try:
                                                condition = input(f"Condition [{selected_game.condition or ''}]: ").strip() or selected_game.condition
                                                source = input(f"Source [{selected_game.source or ''}]: ").strip() or selected_game.source
                                                price = input(f"Price [{selected_game.price or ''}]: ").strip() or selected_game.price
                                                date = self._get_valid_date("Date", selected_game.date)

                                                cursor = conn.cursor()
                                                cursor.execute("""
                                                    UPDATE purchased_games
                                                    SET condition = ?, source = ?, price = ?, acquisition_date = ?
                                                    WHERE physical_game = ?
                                                """, (condition, source, price, date, selected_game.id))
                                                
                                                print("Game updated successfully.")
                                            except EOFError:
                                                print("\nUpdate cancelled")
                                        break
                                    elif choice == "3":
                                        break
                                    else:
                                        print("Invalid choice. Please try again.")
                            else:
                                print("Invalid selection.")
                        except ValueError:
                            print("Invalid input. Please enter a number.")
                except EOFError:
                    print("\nOperation cancelled")
                    return

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
                games = get_wishlist_items(conn, search_term)
                
                if not games:
                    if search_term:
                        print(f"\nNo wishlist items found matching '{search_term}'")
                    else:
                        print("\nYour wishlist is empty")
                    return

                print(f"\nWishlist items{' matching ' + search_term if search_term else ''}:")
                for i, game in enumerate(games):
                    print(f"\n[{i}] {game.name} ({game.console})")
                    try:
                        prices = []
                        if game.price_loose:
                            prices.append(f"loose: ${float(game.price_loose):.2f}")
                        if game.price_complete:
                            prices.append(f"complete: ${float(game.price_complete):.2f}")
                        if game.price_new:
                            prices.append(f"new: ${float(game.price_new):.2f}")
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
                
                # Get the selected game
                selected_game = games[choice]
                
                while True:
                    print("\nOptions:")
                    print("1. Delete game")
                    print("2. Update game")
                    print("3. Cancel")
                    
                    choice = input("\nChoose an option (1-3): ").strip()
                    
                    if choice == "1":
                        confirm = input("Are you sure you want to delete this game? (y/N): ").strip().lower()
                        if confirm == 'y':
                            remove_from_wishlist(conn, selected_game.id)
                            print("Game removed from wishlist")
                        break
                    elif choice == "2":
                        print("\nEnter new values (or press Enter to keep current value)")
                        try:
                            updates = {}
                            
                            name = input(f'Name [{selected_game.name}]: ').strip()
                            if name:
                                updates['name'] = name
                            
                            console = input(f'Console [{selected_game.console}]: ').strip()
                            if console:
                                updates['console'] = console

                            condition = input(f'Condition [{selected_game.condition}]: ').strip().lower()
                            if condition:
                                updates['condition'] = condition

                            if not updates:
                                print("No changes made")
                            else:
                                update_wishlist_item(conn, selected_game.id, updates)
                                print("Changes saved")
                        except (ValueError, EOFError):
                            print("\nEdit cancelled")
                        break
                    elif choice == "3":
                        break
                    else:
                        print("Invalid choice")

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
