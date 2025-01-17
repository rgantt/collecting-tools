#!/usr/local/bin/python3

import argparse
import sqlite3

def display_actions():
    txt = """
[0] - Exit
[1] - Add a game to your library
[2] - Display this message
"""
    print(txt)

def add_game():
    print("We'll add game to the library interactively. I need some info from you.")

    title = input('Title: ')
    console = input('Console: ')
    condition = input('Condition: ')
    source = input('Source: ')
    price = input('Price: ')
    date = input('Date: ')

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

    primary_record = (date, source, price, title, console, condition)
    pricecharting_record = (title, console)

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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='ProgramName',
        description='What the program does'
    )
    parser.add_argument('-d', '--db', required=True)
    args = parser.parse_args()

    display_actions()

    while True:
        action = int(input('What would you like to do? '))

        match action:
            case 0:
                break
            case 1:
                add_game()
            case 2:
                display_actions()
            case _:
                print(f"{action} is not a valid option")
                display_actions()
            
