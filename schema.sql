CREATE TABLE physical_games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    acquisition_date TIMESTAMP,
    source TEXT,
    price DECIMAL,
    name TEXT NOT NULL,
    console TEXT NOT NULL,
    upc INTEGER,
    condition TEXT
);

CREATE TABLE backup_files (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	path TEXT NOT NULL
);

CREATE TABLE physical_games_backup_files (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	physical_game INTEGER NOT NULL,
	backup_file INTEGER NOT NULL
);

create table pricecharting_games (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	pricecharting_id INTEGER UNIQUE,
	name TEXT NOT NULL,
	console TEXT NOT NULL,
	url TEXT NOT NULL
);

create table pricecharting_games_upcs (
	pricecharting_game INTEGER NOT NULL,
	upc INTEGER NOT NULL
);

create table physical_games_pricecharting_games (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	physical_game INTEGER NOT NULL,
	pricecharting_game INTEGER NOT NULL,

	FOREIGN KEY (physical_game) REFERENCES physical_games (id),
	FOREIGN KEY (pricecharting_game) REFERENCES pricecharting_games (id)
);

CREATE TABLE pricecharting_prices (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	retrieve_time TIMESTAMP,
	pricecharting_id INTEGER NOT NULL,
	condition TEXT,
	price DECIMAL,

	FOREIGN KEY (pricecharting_id) REFERENCES pricecharting_games (pricecharting_id)
);

CREATE VIEW IF NOT EXISTS latest_prices AS
SELECT
	g.name,
	g.console,
	z.pricecharting_id,
	max(p.retrieve_time) as retrieve_time,
	p.price,
	p.condition
FROM physical_games g
JOIN physical_games_pricecharting_games j
	ON g.id = j.physical_game
JOIN pricecharting_games z
	ON j.pricecharting_game = z.id
JOIN pricecharting_prices p
	ON z.pricecharting_id = p.pricecharting_id
WHERE p.condition = g.condition
GROUP BY g.id
ORDER BY g.name ASC;