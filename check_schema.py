import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "campusclub.db")

print("DATABASE USED:")
print(DB)
print()

connection = sqlite3.connect(DB)

print("CERTIFICATES TABLE:")
columns = connection.execute("PRAGMA table_info(certificates)").fetchall()

if not columns:
    print("❌ certificates table does NOT exist")
else:
    for column in columns:
        print(f"{column[1]}  |  {column[2]}")

print("\nDATABASE TABLES:")
tables = connection.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type='table'
    ORDER BY name
""").fetchall()

for table in tables:
    print("-", table[0])

connection.close()