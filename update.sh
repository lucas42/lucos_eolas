#!/bin/sh
set -e

docker compose up --build --detach --wait
docker compose exec app python manage.py makemigrations
docker cp lucos_eolas_app:/usr/src/app/lucos_eolas/metadata/migrations/ app/lucos_eolas/metadata
docker compose exec app python manage.py makemessages --all
docker cp lucos_eolas_app:/usr/src/app/lucos_eolas/locale app/lucos_eolas/
docker compose stop