Assume you have a `games.db` SQLite database with `.schema` matching the contents of `schema.sql`.

## Resolving identifiers (bootstrap)

You really only need to do this once.

```bash
# Grab the name,console pairs from the DB (these need to be "cleaned" and match PC)
% sqlite3 games.db "select name || ',' || console from pricecharting_games order by name asc" > input/games.txt

# Retrieve the PC ids for the games
% python3 -u retrieve_ids.py input/games.txt > output/ids.json

# Update 
% python3 -u populate_ids.py output/ids.json games.db
```

Because this really only needs to be done once per game you track, I'd like to work on a "delta"-based one that can be really snappy.

## Resolving identifiers (ongoing/delta)

Use this if you've added a few games to `physical_games` and now you want to resolve identifiers so you can start to grab prices:

```bash
# Grab the name,console pairs from the DB view that can detect unresolved identifiers
% sqlite3 games.db "select title_name || ',' || console from missing_identifiers" > input/games.delta.txt

# From here, same steps as above...

# Retrieve the PC ids for the games
% python3 -u retrieve_ids.py input/games.delta.txt > output/ids.delta.json

# Update
% python3 -u populate_ids.py output/ids.delta.json games.db
```

Note that you should expect some failures here occasionally since the pricecharting titles are usually significantly different than the spine titles for most games. Failures will be appended to `input/games.delta.txt` and you'll want to review them, correct them, and re-run the process.

## Capturing prices

Grab price observations for all of the games in your database--these records are timestamped, so you want to run this on a recurring basis.

```bash
# Grab the PC ids from the DB--assumes you've resolved identifiers already
% sqlite3 games.db "select pricecharting_id from pricecharting_games order by name asc" > input/ids.txt

# Retrieve the prices (loose, used, new) based on the ids
% python3 -u retrieve_prices.py input/ids.txt > output/prices.json

# Insert (a new set of timestamped price observations)
% python3 -u populate_prices.py output/prices.json games.db
```

Because the prices don't really change that much, it would be cool to have a batch job that grabs a handful of randomly-selected titles and grabs their prices on a daily or weekly basis.