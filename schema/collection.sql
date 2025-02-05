BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS physical_games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL,
    console TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backup_files (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS physical_games_backup_files (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	physical_game INTEGER NOT NULL,
	backup_file INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS pricecharting_games (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	pricecharting_id INTEGER UNIQUE,
	name TEXT NOT NULL,
	console TEXT NOT NULL,
	url TEXT
);

CREATE TABLE IF NOT EXISTS pricecharting_games_upcs (
	pricecharting_game INTEGER NOT NULL,
	upc INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS physical_games_pricecharting_games (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	physical_game INTEGER NOT NULL,
	pricecharting_game INTEGER NOT NULL,

	FOREIGN KEY (physical_game) REFERENCES physical_games (id),
	FOREIGN KEY (pricecharting_game) REFERENCES pricecharting_games (id)
);

CREATE TABLE IF NOT EXISTS pricecharting_prices (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	retrieve_time TIMESTAMP,
	pricecharting_id INTEGER NOT NULL,
	condition TEXT,
	price DECIMAL,

	FOREIGN KEY (pricecharting_id) REFERENCES pricecharting_games (pricecharting_id)
);

CREATE TABLE IF NOT EXISTS purchased_games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    physical_game INTEGER NOT NULL,
    acquisition_date DATE NOT NULL CHECK (acquisition_date IS strftime('%Y-%m-%d', acquisition_date)),
    source TEXT,
    price DECIMAL,
    condition TEXT,
    
    FOREIGN KEY (physical_game) REFERENCES physical_games (id)
);

CREATE TABLE IF NOT EXISTS wanted_games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    physical_game INTEGER NOT NULL,
    
    FOREIGN KEY (physical_game) REFERENCES physical_games (id)
);

-- Add condition column to wanted_games if it doesn't exist
ALTER TABLE wanted_games ADD COLUMN condition TEXT DEFAULT 'complete';

-- Update existing wishlist items to use 'complete' condition
UPDATE wanted_games SET condition = 'complete' WHERE condition IS NULL;

CREATE VIEW IF NOT EXISTS latest_prices AS
WITH base_games AS (
    SELECT 
        g.id, 
        g.name, 
        g.console,
        pg.condition as purchased_condition,
        w.condition as wanted_condition,
        CASE WHEN w.id IS NOT NULL THEN 1 ELSE 0 END as is_wanted
    FROM physical_games g
    LEFT JOIN purchased_games pg ON g.id = pg.physical_game
    LEFT JOIN wanted_games w ON g.id = w.physical_game
)
SELECT
    g.name,
    g.console,
    z.pricecharting_id,
    max(p.retrieve_time) as retrieve_time,
    p.price,
    p.condition,
    g.is_wanted,
    COALESCE(g.wanted_condition, g.purchased_condition) as item_condition
FROM base_games g
JOIN physical_games_pricecharting_games j
    ON g.id = j.physical_game
JOIN pricecharting_games z
    ON j.pricecharting_game = z.id
LEFT JOIN pricecharting_prices p
    ON z.pricecharting_id = p.pricecharting_id
GROUP BY g.id, p.condition
ORDER BY g.name ASC;

CREATE VIEW IF NOT EXISTS eligible_price_updates AS
WITH latest_updates AS (
    -- Get the most recent update time for each game, even if prices were null
    SELECT 
        pricecharting_id,
        MAX(retrieve_time) as last_update
    FROM pricecharting_prices
    GROUP BY pricecharting_id
)
SELECT DISTINCT
    g.name,
    g.console,
    z.pricecharting_id
FROM physical_games g
LEFT JOIN purchased_games pg
    ON g.id = pg.physical_game
JOIN physical_games_pricecharting_games j
    ON g.id = j.physical_game
JOIN pricecharting_games z
    ON j.pricecharting_game = z.id
LEFT JOIN latest_updates lu
    ON z.pricecharting_id = lu.pricecharting_id
WHERE lu.last_update IS NULL  -- Never attempted
   OR datetime(lu.last_update) < datetime('now', '-7 days')  -- Or old attempt (even if it was null)
ORDER BY g.name ASC;

COMMIT;