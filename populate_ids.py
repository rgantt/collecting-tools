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
        updates.append((record['pricecharting_id'], record['url'], record['id'],))

    con = sqlite3.connect(dbname)
    with con:
        con.executemany("UPDATE pricecharting_games SET pricecharting_id=?, url=? WHERE id=?", updates)
        print("Committed.")
    con.close()

if __name__ == '__main__':
    main()
