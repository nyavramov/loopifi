# wait for db to start
sleep 10;

# Create the database
flask db upgrade
