-- Ejecutar con psql conectado como postgres a la base postgres.
-- Fuera de una transacción. No ejecutar con el Query Tool de pgAdmin si envuelve en BEGIN.
-- Solicita contraseñas, sin dejarlas guardadas en Git.
\set ON_ERROR_STOP on
\prompt 'Contraseña del rol sweetpets_dev: ' dev_password
\prompt 'Contraseña del rol sweetpets_test: ' test_password
CREATE ROLE sweetpets_dev LOGIN PASSWORD :'dev_password' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE sweetpets_test LOGIN PASSWORD :'test_password' NOSUPERUSER CREATEDB NOCREATEROLE;
CREATE DATABASE sweetpets_dev OWNER sweetpets_dev ENCODING 'UTF8';
CREATE DATABASE sweetpets_test OWNER sweetpets_test ENCODING 'UTF8';
\connect sweetpets_dev
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO sweetpets_dev;
\connect sweetpets_test
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO sweetpets_test;
-- Las tablas se crean con python manage.py migrate.
-- El rol de pruebas puede crear test_sweetpets_test; nunca usarlo en producción.
