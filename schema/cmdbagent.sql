-- Inventory identity, authenticated by the matching Linux account.
CREATE USER IF NOT EXISTS '@AGENT@'@'localhost' IDENTIFIED VIA unix_socket;
ALTER USER '@AGENT@'@'localhost' IDENTIFIED VIA unix_socket;
GRANT SHOW DATABASES ON *.* TO '@AGENT@'@'localhost';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT ON *.* TO '@AGENT@'@'localhost';
