Assume you have a `games.db` SQLite database with `.schema` matching the contents of `schema.sql`. I strongly recommend an automated backup of this file.

## Adding a game to your collection

This is the primary way to add a game to your collection:

```bash
# Add a game to your collection--all fields required
% python3 -u add.py games.db
```

This opens up a prompt to fill in the details of the game you're adding (and you can add multiple games at once).

For now, you still need to follow the "Resolving identifiers" process below to establish that. Until you do so, the "retrieving prices" process will skip this game.

## Resolving identifiers

Use this if you've added a few games to `physical_games` and now you want to resolve identifiers so you can start to grab prices:

```bash
# Retrieve the PC ids for the games
% python3 -u retrieve_ids.py games.db
```

You should expect some failures here occasionally: pricecharting titles can be different than spine titles for most games.

Failures will be shown on the console; correct them by updating values in the `name` and `console` columns in the `pricecharting_games` table as required, and then re-run the `retrieve_ids.py` script. Successes will be written to the database.

### Identifying failures

Use this query to identify the games that failed:

```sql
SELECT * FROM pricecharting_games WHERE pricecharting_id IS NULL
```

## Capturing prices

Grab price observations for all of the games in your database--these records are timestamped, so you want to run this on a recurring basis.

```bash
# Retrieve the prices (loose, used, new) based on the ids
% python3 -u retrieve_prices.py games.db
```

This will only retrieve prices for games that have not been retrieved in the last 3 days.