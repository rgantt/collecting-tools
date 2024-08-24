Assume you have a `games.db` SQLite database with `.schema` matching the contents of `schema.sql`.

## Resolving identifiers

```
# Grab the name,console pairs from the DB (these need to be "cleaned" and match PC)
% sqlite3 games.db "select name || ',' || console from pricecharting_games order by name asc" > input/games.txt
# Retrieve the PC ids for the games
% python3 -u retrieve_ids.py input/games.txt > output/ids.json
# Update 
% python3 -u populate_ids.py output/ids.json games.db
```

## Capturing prices

```
% TODO
```