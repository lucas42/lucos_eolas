# lucos_eolas
Personal metadata &amp; ontology manager

## Requirements
* Docker
* Docker Compose

## Architecture
Has three components:
* db - a postgres database
* app - a Django app served using gunicorn
* web - an nginx server for routing traffic to app and serving static files

## Running in Production
`docker compose up -d --no-build`

## Running locally
`docker compose up --build`

## Database commands
### Manually creating a backup
(on machine with docker installed)
* `docker exec lucos_eolas_db pg_dump --user postgres postgres > /tmp/eolas.sql`

### Wiping database clean so restore doesn't cause any conflicts
(on machine with docker & docker-compose installed)
* `docker compose exec db dropdb --user postgres postgres`
* `docker compose exec db createdb --user postgres postgres`

### Restoring from backup
(on machine with docker & docker-compose installed)
Assuming the backup file is available on the current machine's /tmp directory, run the following commands:

* `docker compose cp /tmp/eolas.sql db:/tmp/`
* `docker compose exec db sh -c 'dropdb --user postgres postgres && createdb --user postgres postgres'` (To wipe data, if there's an existing DB)
* `docker compose exec db sh -c 'psql --user postgres postgres < /tmp/eolas.sql'`

## Helper script for updating migration & translation files locally

`./update.sh`

Depends on docker compose.  This script will start the containers, run the appropriate `makemigrations` & `makemessages` commands, copy the relevant files to the local filesystem and stop the containers again.