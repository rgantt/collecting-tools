from flask import Flask, request, render_template, jsonify
from pathlib import Path
from contextlib import contextmanager
import sqlite3
from lib.collection_utils import get_wishlist_items
from urllib.parse import urlencode
from werkzeug.datastructures import MultiDict

app = Flask(__name__)
db_path = Path("games.db")

# Add built-in functions to Jinja environment
app.jinja_env.globals.update(min=min, max=max, range=range)

# Helper function for updating URL parameters
def update_url_params(args, **kwargs):
    if not isinstance(args, MultiDict):
        args = MultiDict(args)
    params = args.copy()
    for key, value in kwargs.items():
        params[key] = value
    return '?' + urlencode(params)

# Register template filter
app.template_filter('update_url_params')(update_url_params)

@contextmanager
def get_db():
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()

def get_collection_games(page=1, per_page=30, sort_by='acquisition_date', sort_order='desc'):
    """Get paginated list of games in the collection."""
    sort_field = get_sort_field(sort_by)
    sort_direction = 'DESC' if sort_order.lower() == 'desc' else 'ASC'
    
    with get_db() as db:
        cursor = db.cursor()
        
        # Get paginated games with their latest prices
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
                pg.condition,
                s.name as source,
                pg.price as purchase_price,
                CAST(lp.price AS DECIMAL) as current_price,
                pg.acquisition_date as date
            FROM physical_games p
            JOIN purchased_games pg ON p.id = pg.physical_game
            LEFT JOIN sources s ON pg.source = s.name
            LEFT JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
            LEFT JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
            LEFT JOIN latest_prices lp ON pc.pricecharting_id = lp.pricecharting_id 
                AND LOWER(lp.condition) = LOWER(pg.condition)
                AND lp.rn = 1
            ORDER BY {sort_field} {sort_direction}, p.name
            LIMIT ? OFFSET ?
        """, (per_page, (page - 1) * per_page))
        
        collection_games = []
        for row in cursor.fetchall():
            name, console, condition, source, purchase_price, current_price, date = row
            collection_games.append({
                'name': name,
                'console': console,
                'condition': condition,
                'source': source,
                'purchase_price': float(purchase_price) if purchase_price else None,
                'current_price': float(current_price) if current_price else None,
                'date': date
            })
        
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
        'name': 'p.name',
        'console': 'p.console',
        'condition': 'pg.condition',
        'source': 's.name',
        'purchase_price': 'pg.price',
        'current_price': 'lp.price',
        'acquisition_date': 'pg.acquisition_date'
    }
    return valid_sort_fields.get(sort_by, 'pg.acquisition_date')

def get_wishlist_sort_field(sort_by: str) -> str:
    valid_sort_fields = {
        'name': 'p.name',
        'console': 'p.console',
        'price_complete': 'CAST(lp_complete.price AS DECIMAL)',
        'price_loose': 'CAST(lp_loose.price AS DECIMAL)',
        'price_new': 'CAST(lp_new.price AS DECIMAL)'
    }
    return valid_sort_fields.get(sort_by, 'p.name')

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 30
    sort_by = request.args.get('sort', 'acquisition_date')
    sort_order = request.args.get('order', 'desc')
    wishlist_sort = request.args.get('wishlist_sort', 'name')
    wishlist_order = request.args.get('wishlist_order', 'asc')

    app.logger.info(f'Page: {page}, Sort: {sort_by}, Order: {sort_order}')
    
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

@app.route('/api/collection')
def get_all_collection_games():
    sort_by = request.args.get('sort', 'acquisition_date')
    sort_order = request.args.get('order', 'desc')
    
    sort_field = get_sort_field(sort_by)
    sort_direction = 'DESC' if sort_order == 'desc' else 'ASC'
    
    with get_db() as conn:
        cursor = conn.cursor()
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
                pg.condition,
                s.name as source,
                pg.price as purchase_price,
                CAST(lp.price AS DECIMAL) as current_price,
                pg.acquisition_date as date
            FROM physical_games p
            JOIN purchased_games pg ON p.id = pg.physical_game
            LEFT JOIN sources s ON pg.source = s.name
            LEFT JOIN physical_games_pricecharting_games pcg ON p.id = pcg.physical_game
            LEFT JOIN pricecharting_games pc ON pcg.pricecharting_game = pc.id
            LEFT JOIN latest_prices lp ON pc.pricecharting_id = lp.pricecharting_id 
                AND LOWER(lp.condition) = LOWER(pg.condition)
                AND lp.rn = 1
            ORDER BY {sort_field} {sort_direction}, p.name
        """)
        
        games = []
        for row in cursor.fetchall():
            name, console, condition, source, purchase_price, current_price, date = row
            games.append({
                'name': name,
                'console': console,
                'condition': condition,
                'source': source,
                'purchase_price': float(purchase_price) if purchase_price else None,
                'current_price': float(current_price) if current_price else None,
                'date': date
            })
        
        app.logger.info(f'API: Returning {len(games)} collection games')
        return jsonify(games)

@app.route('/api/wishlist')
def get_all_wishlist():
    sort_by = request.args.get('sort', 'name')
    sort_order = request.args.get('order', 'asc')
    
    sort_field = get_wishlist_sort_field(sort_by)
    sort_direction = 'DESC' if sort_order == 'desc' else 'ASC'
    
    with get_db() as conn:
        cursor = conn.cursor()
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
        
        games = []
        for row in cursor.fetchall():
            name, console, price_complete, price_loose, price_new = row
            games.append({
                'name': name,
                'console': console,
                'price_complete': float(price_complete) if price_complete else None,
                'price_loose': float(price_loose) if price_loose else None,
                'price_new': float(price_new) if price_new else None
            })
        
        app.logger.info(f'Returning {len(games)} wishlist games')
        return jsonify(games)

if __name__ == '__main__':
    app.run(debug=True, port=5004)
