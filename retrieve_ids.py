import argparse
import json
from id_retrieval import retrieve_games, get_game_id, insert_game_ids
import sqlite3

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('db_path', help='Path to SQLite database')
    args = parser.parse_args()

    games = retrieve_games(args.db_path)
    if not games:
        print("No unidentified games found.")
        return

    print(f"Retrieving identifiers for {len(games)} games:")

    failed = []
    retrieved = []
    for id, name, console in games:
        try:
            print(f"{name} on {console}...")
            data = get_game_id(id, name, console)
            retrieved.append(data)
        except ValueError as err:
            msg = f"Could not retrieve info: {err}"
            failed.append({'game': id, 'name': name, 'message': msg})
    
    if retrieved:
        try:
            records_inserted = insert_game_ids(retrieved, args.db_path)
            print(f"Saved {records_inserted} records to database")
        except sqlite3.Error as e:
            print(f"Failed to save records to database: {e}")

    if failed:
        print("\nFailures:")
        print(json.dumps(failed, indent=2))

if __name__ == '__main__':
    main()
