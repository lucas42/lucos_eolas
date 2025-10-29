# lucos Eolas - Django app

## Dependencies
* django
* A database (and the relevant python libraries to use that database)

## Creating a new database migration

* Upgrade the approprite `models.py` files
* `docker compose exec app python manage.py makemigrations`
* `docker cp lucos_eolas_app:/usr/src/app/lucos_eolas/metadata/migrations/ app/lucos_eolas/metadata`
* Rebuild & restart the container for the migrations to take effect.
* Commit the new migration files to git

## Language support
The UI is available in English or Irish languages.  Irish is the default and this can be switched in the navigation bar.  The source files are written in English, with locale config provided for Irish in `lucos_eolas/locale/ga/LC_MESSAGE/django.po`.

## Updating Translations

* `docker compose exec app python manage.py makemessages --all`
* `docker cp lucos_eolas_app:/usr/src/app/lucos_eolas/locale app/lucos_eolas/`
* Update the `.po` files in the locale directory with the relevant languages
* Rebuild & restart the container for the translations to take effect.  (translations are compiled as part of the docker build process)
* Commit the locale files to git

## Data Imports

### Importing Language Families from Library of Congress

Run the command:
`docker compose exec app python manage.py load_language_families`