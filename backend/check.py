import sqlite3
c = sqlite3.connect('instance/rezerv.db')
print(c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())