### Performing a database migration with flask-migrate

1. **(Optional. Warning: DELETES ALL DATABASE DATA):** If you want to make absolutely sure there's nothing wrong with the database and don't mind deleting all information, you can clear the current database. Login to the database: `mysql -u root -pnevergonnagiveyouup` (or whatever your user:password is). Then `show databases;` Choose which database you'd like to delete: `drop database loops;`. Recreate the schema: `create schema loops;` Exit mysql: `ctrl + c`.

2. Clone the repo and cd into it:`git clone git@gitlab.com:nyavramov/discover_loops_web.git && cd discover_loops_web`

3. Upgrade the current database to the latest migration: `flask db upgrade`

4. Make a change to the schema. In this example, we’ll add a new column to record by adding `url = db.Column(db.String(128), default=None)` in the `main.py` file. Save the file.

5. Migrate the database to reflect the changes to the schema: `flask db migrate`.You should receive a message like: `Detected added column record.url`
