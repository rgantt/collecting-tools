import argparse
import sqlite3

##
# python3 add.py \
#   --title $TITLE \
#   --console $CONSOLE \
#   --condition $CONDITION \
#   --source $SOURCE \
#   --price $PRICE
##
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='ProgramName',
        description='What the program does'
    )

    parser.add_argument('-d', '--db', required=True)
    parser.add_argument('-t', '--title', required=True)
    parser.add_argument('-c', '--console', required=True)

    parser.add_argument('--condition', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--price', required=True)
    parser.add_argument('--date', required=True)

    args = parser.parse_args()

    primary_insert="""
    insert into physical_games
    (acquisition_date, source, price, name, console, condition)
    values
    (?,?,?,?,?,?)
    """
    pricecharting_insert="""
    insert into pricecharting_games
    (name, console)
    values
    (?,?)
    """
    join_insert="""
    insert into physical_games_pricecharting_games
    (physical_game, pricecharting_game)
    values
    (?,?)
    """

    primary_record = (args.date, args.source, args.price, args.title, args.console, args.condition)
    pricecharting_record = (args.title, args.console)

    con = sqlite3.connect(args.db)
    with con:
        cursor = con.cursor()
        cursor.execute(primary_insert, primary_record)
        first_id=cursor.lastrowid
        cursor.execute(pricecharting_insert, pricecharting_record)
        second_id=cursor.lastrowid
        cursor.execute(join_insert, (first_id, second_id))
    print("Committed")
    con.close()
