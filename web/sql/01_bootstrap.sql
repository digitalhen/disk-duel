-- One-time bootstrap on the target Postgres instance.
-- Run as the `postgres` superuser.
-- The actual schema is managed by Alembic (see alembic/versions/).

-- Replace the password before applying. Generate one with:
--     openssl rand -base64 24

CREATE ROLE diskduel WITH LOGIN PASSWORD '__REPLACE_ME__';

CREATE DATABASE diskduel OWNER diskduel;

-- Allow the shared `readonly` role to read this DB too. Optional.
GRANT CONNECT ON DATABASE diskduel TO readonly;

-- Switch to the diskduel DB:
\c diskduel

GRANT USAGE ON SCHEMA public TO readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE diskduel IN SCHEMA public
    GRANT SELECT ON TABLES TO readonly;
