CREATE TABLE IF NOT EXISTS companies (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

INSERT INTO companies (name) VALUES ('Ambev'), ('Eurofarma'), ('Nubank');
