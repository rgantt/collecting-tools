import json
import sys
import sqlite3

filename=sys.argv[1]
dbname=sys.argv[2]

statement="""
INSERT INTO pricecharting_prices 
(pricecharting_id, retrieve_time, price, condition)
VALUES 
(?,?,?,?)
"""

def main():
    with open(filename) as file:
        games = json.load(file)

    records = []
    for record in games:
        prices = record['prices']
        records.append((record['game'], record['time'], prices['new'], 'new',))
        records.append((record['game'], record['time'], prices['loose'], 'loose',))
        records.append((record['game'], record['time'], prices['complete'], 'complete',))

    con = sqlite3.connect(dbname)
    with con:
        con.executemany(statement, records)
    print(f"Committed {len(games)} records.")
    con.close()

if __name__ == '__main__':
    main()
