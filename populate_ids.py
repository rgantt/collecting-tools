import json
import sys
import sqlite3

filename=sys.argv[1]
dbname=sys.argv[2]

def main():
    with open(filename) as file:
        games = json.load(file)

    updates = []
    for record in games:
        updates.append((record['pricecharting_id'], record['url'], record['id'], record['name'], record['console']))

    con = sqlite3.connect(dbname)
    with con:
        con.executemany("REPLACE INTO pricecharting_games (pricecharting_id, url, id, name, console) VALUES (?,?,?,?,?)", updates)
        print(f"Committed {len(games)} records.")
    con.close()

if __name__ == '__main__':
    main()
