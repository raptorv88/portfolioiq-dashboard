import sqlite3
conn = sqlite3.connect('portfolio_data.db')
conn.execute('ALTER TABLE snapshots ADD COLUMN buy_trades_json TEXT DEFAULT "[]"')
conn.commit()
conn.close()
print('Done')