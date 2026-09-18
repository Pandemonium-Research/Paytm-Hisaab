-- Separate databases keep local workflow and memory experiments away from the ledger database.
--
-- SQL, not a shell script: the postgres entrypoint pipes .sql files through psql, so nothing has
-- to be executable. A .sh here passed the entrypoint's -x check but still failed with "bad
-- interpreter: Permission denied" from the bind mount on Docker Desktop for macOS, and exec bits on
-- bind mounts are no more reliable under WSL2. When it failed, postgres exited, restarted, skipped
-- initialisation because the data directory now existed, and these databases were never created.
SELECT 'CREATE DATABASE cognee'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'cognee')\gexec

SELECT 'CREATE DATABASE "n8n-local"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'n8n-local')\gexec
