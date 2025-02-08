from flask import Blueprint, request, render_template, jsonify, session, current_app
from werkzeug.datastructures import MultiDict
from urllib.parse import urlencode
from contextlib import contextmanager
import sqlite3
from pathlib import Path
from app.auth import requires_auth

main = Blueprint('main', __name__)

db_path = Path(__file__).parent.parent / "games.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()

# Helper function for updating URL parameters
def update_url_params(args, **kwargs):
    if not isinstance(args, MultiDict):
        args = MultiDict(args)
    params = args.copy()
    for key, value in kwargs.items():
        params[key] = value
    return '?' + urlencode(params)

def get_collection_games(page=1, per_page=30, sort_by='acquisition_date', sort_order='desc'):
    """Get paginated list of games in the collection."""
    sort_field = get_sort_field(sort_by)
    sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
    
    current_app.logger.info(f'Getting collection games with sort_field={sort_field}, direction={sort_direction}, page={page}, per_page={per_page}')
    
    with get_db() as db:
        cursor = db.cursor()
        
        # Get paginated games with their latest prices
        query = f"""
            WITH latest_prices AS (
                SELECT 
                    pricecharting_id,
                    condition,
                    price,
                    ROW_NUMBER() OVER (PARTITION BY pricecharting_id, condition ORDER BY retrieve_time DESC) as rn
                FROM pricecharting_prices
            ),
            games_with_prices AS (
                SELECT 
                    p.id as id,
                    p.name as name,
                    p.console as console,
                    COALESCE(w.condition, pg.condition) as condition,
                    s.name as source_name,
                    CAST(pg.price AS DECIMAL) as purchase_price,
                    CAST(lp.price AS DECIMAL) as current_price,
                    pg.acquisition_date as date,
                    CASE WHEN w.physical_game IS NOT NULL THEN 1 ELSE 0 END as is_wanted
                FROM physical_games p
                LEFT JOIN purchased_games pg ON p.id = pg.physical_game
                LEFT JOIN wanted_games w ON p.id = w.physical_game
                LEFT JOIN sources s ON pg.source = s.name
                LEFT JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
                LEFT JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
                LEFT JOIN latest_prices lp ON pc.pricecharting_id = lp.pricecharting_id 
                    AND (
                        (pg.condition IS NOT NULL AND LOWER(lp.condition) = LOWER(pg.condition))
                        OR 
                        (w.condition IS NOT NULL AND LOWER(lp.condition) = LOWER(w.condition))
                    )
                    AND lp.rn = 1
                WHERE pg.physical_game IS NOT NULL OR w.physical_game IS NOT NULL
            )
            SELECT *
            FROM games_with_prices
            ORDER BY 
                CASE WHEN {sort_field} IS NULL THEN 1 ELSE 0 END,
                {sort_field} {sort_direction},
                name ASC
            LIMIT ? OFFSET ?
        """
        current_app.logger.info(f'Executing query: {query}')
        cursor.execute(query, (per_page, (page - 1) * per_page))
        
        collection_games = []
        for row in cursor.fetchall():
            id, name, console, condition, source, purchase_price, current_price, date, is_wanted = row
            collection_games.append({
                'id': id,
                'name': name,
                'console': console,
                'condition': condition,
                'source': source or None,
                'purchase_price': float(purchase_price) if purchase_price else None,
                'current_price': float(current_price) if current_price else None,
                'date': date,
                'is_wanted': bool(is_wanted)
            })
        
        current_app.logger.info(f'Found {len(collection_games)} games')
        return collection_games

def get_wishlist_items_sorted(wishlist_sort='name', wishlist_order='asc'):
    sort_field = get_wishlist_sort_field(wishlist_sort)
    sort_direction = 'DESC' if wishlist_order == 'desc' else 'ASC'
    
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute(f"""
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
                CAST(lp_complete.price AS DECIMAL) as price_complete,
                CAST(lp_loose.price AS DECIMAL) as price_loose,
                CAST(lp_new.price AS DECIMAL) as price_new
            FROM wanted_games w
            JOIN physical_games p ON w.physical_game = p.id
            LEFT JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
            LEFT JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
            LEFT JOIN latest_prices lp_complete ON pc.pricecharting_id = lp_complete.pricecharting_id 
                AND LOWER(lp_complete.condition) = 'complete'
                AND lp_complete.rn = 1
            LEFT JOIN latest_prices lp_loose ON pc.pricecharting_id = lp_loose.pricecharting_id 
                AND LOWER(lp_loose.condition) = 'loose'
                AND lp_loose.rn = 1
            LEFT JOIN latest_prices lp_new ON pc.pricecharting_id = lp_new.pricecharting_id 
                AND LOWER(lp_new.condition) = 'new'
                AND lp_new.rn = 1
            ORDER BY {sort_field} {sort_direction}, p.name
        """)
        
        wishlist = []
        for row in cursor.fetchall():
            name, console, price_complete, price_loose, price_new = row
            wishlist.append({
                'name': name,
                'console': console,
                'price_complete': float(price_complete) if price_complete else None,
                'price_loose': float(price_loose) if price_loose else None,
                'price_new': float(price_new) if price_new else None
            })
        
        return wishlist

def get_sort_field(sort_by: str) -> str:
    valid_sort_fields = {
        'name': 'name',
        'console': 'console',
        'condition': 'condition',
        'source': 'source_name',
        'purchase_price': 'purchase_price',
        'current_price': 'current_price',
        'date': 'date',
        'acquisition_date': 'date'
    }
    return valid_sort_fields.get(sort_by, 'date')

def get_wishlist_sort_field(sort_by: str) -> str:
    valid_sort_fields = {
        'name': 'p.name',
        'console': 'p.console',
        'price_complete': 'CAST(lp_complete.price AS DECIMAL)',
        'price_loose': 'CAST(lp_loose.price AS DECIMAL)',
        'price_new': 'CAST(lp_new.price AS DECIMAL)'
    }
    return valid_sort_fields.get(sort_by, 'p.name')

@main.route('/')
@requires_auth
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 30
    sort_by = request.args.get('sort', 'acquisition_date')
    sort_order = request.args.get('order', 'desc')
    wishlist_sort = request.args.get('wishlist_sort', 'name')
    wishlist_order = request.args.get('wishlist_order', 'asc')

    current_app.logger.info(f'Page: {page}, Sort: {sort_by}, Order: {sort_order}')
    
    # Get total count for pagination
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM purchased_games pg JOIN physical_games p ON pg.physical_game = p.id")
        total_items = cursor.fetchone()[0]
    
    total_pages = (total_items + per_page - 1) // per_page

    collection_games = get_collection_games(page, per_page, sort_by, sort_order)
    wishlist_items = get_wishlist_items_sorted(wishlist_sort, wishlist_order)

    return render_template('index.html',
                         collection_games=collection_games,
                         wishlist=wishlist_items,
                         current_page=page,
                         total_pages=total_pages,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         wishlist_sort=wishlist_sort,
                         wishlist_order=wishlist_order)

@main.route('/api/collection')
@requires_auth
def get_all_collection_games():
    """Get all games for client-side operations."""
    # Use existing function but get all games without pagination
    collection_games = get_collection_games(page=1, per_page=10000)  # Large number to get all games
    return jsonify(collection_games)
