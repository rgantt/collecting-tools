import argparse
import json
from price_retrieval import retrieve_games, process_batch, insert_price_records

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('db_path', help='Path to SQLite database')
    parser.add_argument('--batch-size', type=int, default=50, help='Maximum number of games to process in each batch')
    parser.add_argument('--max-prices', type=int, help='Maximum number of prices to retrieve')
    args = parser.parse_args()

    games = retrieve_games(args.db_path, args.max_prices)
    if not games:
        print("No games found with prices older than 3 days.")
        return

    print(f"Retrieving prices for {len(games)} games...")
    all_failed = []
    processed = 0

    for i in range(0, len(games), args.batch_size):
        successful, failed = process_batch(games[i:i + args.batch_size])
        
        if successful:
            try:
                insert_price_records(successful, args.db_path)
                processed += len(successful)
                print(f"Progress: {processed}/{len(games)} prices retrieved")
            except Exception as e:
                print(f"Failed to save batch to database: {e}")
        
        all_failed.extend(failed)
    
    print(f"Completed: {processed}/{len(games)} prices retrieved")
    
    if all_failed:
        print(f"\nFailures ({len(all_failed)}):")
        print(json.dumps(all_failed, indent=2))

if __name__ == '__main__':
    main()
