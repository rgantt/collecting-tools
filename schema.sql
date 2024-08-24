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

create table pricecharting_games (
	id INTEGER PRIMARY KEY AUTOINCREMENT,

	pricecharting_id INTEGER,
	name TEXT NOT NULL,
	console TEXT NOT NULL
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
	pricecharting_game INTEGER NOT NULL,
	new DECIMAL, 
	loose DECIMAL,
	complete DECIMAL,

	FOREIGN KEY (pricecharting_id) REFERENCES pricecharting_games (pricecharting_id)
);