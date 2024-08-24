Assume you have a `games.db` SQLite database with `.schema` matching the contents of `schema.sql`.

## Resolving identifiers

```bash
# Grab the name,console pairs from the DB (these need to be "cleaned" and match PC)
% sqlite3 games.db "select name || ',' || console from pricecharting_games order by name asc" > input/games.txt

# Retrieve the PC ids for the games
% python3 -u retrieve_ids.py input/games.txt > output/ids.json

# Update 
% python3 -u populate_ids.py output/ids.json games.db
```

## Capturing prices

```bash
# Grab the PC ids from the DB--assumes you've resolved identifiers already
% sqlite3 games.db "select pricecharting_id from pricecharting_games order by name asc" > input/ids.txt

# Retrieve the prices (loose, used, new) based on the ids
% python3 -u retrieve_prices.py input/ids.txt > output/prices.json

# TODO: Need to write a populate_prices.py script to shove these into the DB...
```