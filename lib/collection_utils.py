import sqlite3
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass

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

@dataclass
class GameAdditionResult:
    success: bool
    message: str
    game_id: Optional[int] = None

@dataclass
class GameData:
    title: str
    console: str
    condition: str
    source: str
    price: str
    date: str

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
    """Add a game to the database with optional price tracking ID."""
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO physical_games
            (name, console)
            VALUES (?, ?)
        """, (game.title, game.console))
        
        physical_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO purchased_games
            (physical_game, acquisition_date, source, price, condition)
            VALUES (?, ?, ?, ?, ?)
        """, (physical_id, game.date, game.source, game.price, game.condition))

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
    """Add a game to the wishlist with optional price tracking ID."""
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

@dataclass
class WishlistItem:
    id: int
    name: str
    console: str
    pricecharting_id: Optional[str]
    price_complete: Optional[float]
    price_loose: Optional[float]
    price_new: Optional[float]

def get_wishlist_items(conn: sqlite3.Connection, search_term: Optional[str] = None) -> List[WishlistItem]:
    """Get wishlist items from the database, optionally filtered by search term.
    
    Args:
        conn: Database connection
        search_term: Optional search term to filter results
        
    Returns:
        List of WishlistItem objects
    """
    cursor = conn.cursor()
    
    query = """
        SELECT 
            p.id,
            p.name,
            p.console,
            pc.pricecharting_id,
            MAX(CASE WHEN lp.condition = 'complete' THEN lp.price END) as price_complete,
            MAX(CASE WHEN lp.condition = 'loose' THEN lp.price END) as price_loose,
            MAX(CASE WHEN lp.condition = 'new' THEN lp.price END) as price_new
        FROM physical_games p
        JOIN wanted_games w ON p.id = w.physical_game
        LEFT JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
        LEFT JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
        LEFT JOIN latest_prices lp ON pc.pricecharting_id = lp.pricecharting_id
        WHERE 1=1
    """
    
    params = []
    if search_term:
        query += " AND (LOWER(p.name) LIKE LOWER(?) OR LOWER(p.console) LIKE LOWER(?))"
        params = [f'%{search_term}%', f'%{search_term}%']
    
    query += " GROUP BY p.id, p.name, p.console, pc.pricecharting_id ORDER BY p.name ASC"
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    return [
        WishlistItem(
            id=row[0],
            name=row[1],
            console=row[2],
            pricecharting_id=str(row[3]) if row[3] is not None else None,
            price_complete=row[4],
            price_loose=row[5],
            price_new=row[6]
        ) for row in rows
    ]

def update_wishlist_item(conn: sqlite3.Connection, game_id: int, updates: Dict[str, str]) -> None:
    """Update a wishlist item's information.
    
    Args:
        conn: Database connection
        game_id: ID of the game to update
        updates: Dictionary of field names and their new values
    """
    if not updates:
        return
        
    cursor = conn.cursor()
    
    # Update physical_games
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [game_id]
    cursor.execute(f"""
        UPDATE physical_games
        SET {set_clause}
        WHERE id = ?
    """, values)

    # Update pricecharting_games if name/console changed
    if 'name' in updates or 'console' in updates:
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

def remove_from_wishlist(conn: sqlite3.Connection, game_id: int) -> None:
    """Remove a game from the wishlist.
    
    Args:
        conn: Database connection
        game_id: ID of the game to remove
    """
    cursor = conn.cursor()
    cursor.execute("DELETE FROM wanted_games WHERE physical_game = ?", (game_id,))