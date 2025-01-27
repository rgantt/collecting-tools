## Using the REPL

Manage your collection of physical video games with this command-line tool.

```bash
# If games.db doesn't exist, the REPL will prompt you to initialize it
% ./collection.py -d games.db

Available commands:
add      - Add a game to your library
search   - Search library
prices   - Retrieve latest prices
want     - Add a game to the wishlist
wishlist - View your wishlist
help     - Display available commands

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

#### want - Add a game to your wishlist
```bash
What would you like to do? (Ctrl + D to exit) want
Title: Grandia II
Console: Dreamcast
Game added to wishlist successfully
```

#### search - Search and edit games in your collection
```bash
What would you like to do? (Ctrl + D to exit) search
Enter search term: mario

Found 3 games:
[0] Super Mario 64 (N64)
    loose: $52.99 (bought for $45.99 from eBay on 2024-03-15)
    current market prices - loose: $52.99 | complete: $89.99 | new: $299.99

[1] Mario Kart 8 Deluxe (Switch)
    complete: $45.00 (bought for $39.99 from GameStop on 2024-02-01)
    current market prices - loose: $39.99 | complete: $45.00 | new: $59.99

[2] Super Mario RPG (Switch) - WISHLIST
    current market prices - loose: $49.99 | complete: $54.99 | new: $59.99

Select a game to edit (or press Enter to cancel): 0
Delete game from collection? (default: No) [y/N]: y
Game completely deleted from collection
```

#### prices - Update market prices for your games
```bash
What would you like to do? (Ctrl + D to exit) prices
Maximum prices to retrieve (optional): 10
Retrieving prices for 10 games...
Progress: [=========================-----------------] 60.0% (6/10) - Pokemon Scarlet
Updated prices for 10 games
```

#### wishlist - View your wishlist
```bash
What would you like to do? (Ctrl + D to exit) wishlist
Enter search term (or press Enter to show all): mario

Wishlist items matching mario:
[0] Super Mario RPG (Switch)
    loose: $49.99 | complete: $54.99 | new: $59.99

[1] Mario Kart 9 (Switch)
    no current prices

Select a game to edit (or press Enter to cancel): 0
Remove from wishlist? (default: No) [y/N]: y
Game removed from wishlist
```

#### help - Display available commands
```bash
What would you like to do? (Ctrl + D to exit) help

Available commands:
add      - Add a game to your library
search   - Search library
prices   - Retrieve latest prices
ids      - Retrieve missing game IDs
want     - Add a game to the wishlist
wishlist - View your wishlist
help     - Display available commands
```

### Features

- Track your physical game collection with details like:
  - Title
  - Console
  - Condition (loose, CIB, new)
  - Purchase source and price
  - Acquisition date
- Maintain a wishlist of games you want to acquire
- Search your collection and wishlist by name or console
- Edit existing entries
- Automatically fetch and track current market prices from PriceCharting
- Integration with PriceCharting for game identification and price tracking

### Tips

- Dates should be entered in YYYY-MM-DD format
- Use Ctrl+D (or Cmd+D on macOS) to exit the program
- Leave input blank and press Enter to keep existing values when editing
- Games can be removed from your collection or wishlist during editing by typing 'remove'
- The prices command can be limited to process a specific number of games
- Market prices are fetched from PriceCharting.com's database
- Wishlist items only require title and console
- Search is case-insensitive and matches partial text
- You can search by console name (e.g., "Switch" or "PS5") to see all games for that platform