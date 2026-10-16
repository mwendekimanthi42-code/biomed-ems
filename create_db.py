import sqlite3

conn = sqlite3.connect("biomed.db")
conn.executescript(open("database/schema.sql").read())
conn.close()
print("Database created")