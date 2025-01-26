## Using the REPL

Manage your collection of physical video games with this command-line tool.

```bash
# If games.db doesn't exist, the REPL will prompt you to initialize it
% ./collection.py -d games.db

Available commands:
add      - Add a game to your library
search   - Search library
prices   - Retrieve latest prices
ids      - Retrieve missing game IDs

What would you like to do? (Ctrl + D to exit) 
```

### Available Commands

#### add - Add a new game to your collection
```bash
What would you like to do? (Ctrl + D to exit) add
Title: Super Mario 64
Console: N64
Condition: loose
Source: eBay
Price: 45.99
Date: 2024-03-15
Game added successfully
```

#### search - Search and edit games in your collection
```bash
What would you like to do? (Ctrl + D to exit) search
Enter search term: mario

Found 2 games:
[0] Super Mario 64 (N64) - loose condition
    $52.99 (bought for $45.99 from eBay on 2024-03-15)

[1] Mario Kart 8 Deluxe (Switch) - CIB condition
    $45.00 (bought for $39.99 from GameStop on 2024-02-01)

Select a game to edit (or press Enter to cancel): 0
Enter new values (or press Enter to keep current value)
Name [Super Mario 64]: 
Console [N64]: 
Condition [loose]: CIB
Source [eBay]: 
Price [45.99]: 
Date [2024-03-15]: 
Changes saved
```

#### prices - Update market prices for your games
```bash
What would you like to do? (Ctrl + D to exit) prices
Maximum prices to retrieve (optional): 10
Retrieving prices for 10 games...
Progress: [=========================-----------------] 60.0% (6/10) - Pokemon Scarlet
Updated prices for 10 games
```

#### ids - Retrieve PriceCharting IDs for unidentified games
```bash
What would you like to do? (Ctrl + D to exit) ids
Retrieving identifiers for 5 games:
Progress: [==================================================] 100.0% (5/5) - Zelda: Breath of the Wild
Saved 5 records to database
```

### Features

- Track your physical game collection with details like:
  - Title
  - Console
  - Condition (loose, CIB, new)
  - Purchase source and price
  - Acquisition date
- Search your collection by name, console, or condition
- Edit existing entries
- Automatically fetch and track current market prices from PriceCharting
- Integration with PriceCharting for game identification and price tracking

### Tips

- Dates should be entered in YYYY-MM-DD format
- Use Ctrl+D (or Cmd+D on macOS) to exit the program
- Leave input blank and press Enter to keep existing values when editing
- The prices command can be limited to process a specific number of games
- Market prices are fetched from PriceCharting.com's database