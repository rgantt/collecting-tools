Assume you have a `games.db` SQLite database with `.schema` matching the contents of `schema.sql`. I strongly recommend an automated backup of this file.

## Adding a game to your collection

This is the primary way to add a game to your collection:

```bash
% export DB_PATH=games.db

# Add a game to your collection--all fields required
% python3 collection.py \
  --db $DB_PATH \
  --title 'Pokemon Sword and Shield Double Pack' \
  --console "Nintendo Switch" \
  --condition "CIB" \
  --price 95 \
  --source "reddit" \
  --date "2024-08-26"
```

Note that this will not (currently) attempt to populate a mapping between your game and a pricecharting game. For now, you still need to follow the "Resolving identifiers" process below to establish that. Until you do so, the "retrieving prices" process will skip this game.

## Resolving identifiers

Use this if you've added a few games to `physical_games` and now you want to resolve identifiers so you can start to grab prices:

```bash
% export DB_PATH=games.db

# Retrieve the PC ids for the games
% python3 -u retrieve_ids.py $DB_PATH > output/ids.delta.json

# Update
% python3 -u populate_ids.py output/ids.delta.json $DB_PATH
```

Note that you should expect some failures here occasionally since the pricecharting titles are usually significantly different than the spine titles for most games. Failures will be appended to `input/games.delta.txt` and you'll want to review them, correct them, and re-run the process.

## Capturing prices

Grab price observations for all of the games in your database--these records are timestamped, so you want to run this on a recurring basis.

```bash
% export DB_PATH=games.db

# Retrieve the prices (loose, used, new) based on the ids
% python3 -u retrieve_prices.py $DB_PATH > output/prices.json

# Insert (a new set of timestamped price observations)
% python3 -u populate_prices.py output/prices.json $DB_PATH
```

Because the prices don't really change that much, it would be cool to have a batch job that grabs a handful of randomly-selected titles and grabs their prices on a daily or weekly basis.