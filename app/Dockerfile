FROM lucas42/lucos_navbar:2.1.16 AS navbar
FROM python:3.15.0a7-alpine

# set working directory
WORKDIR /usr/src/app

# set environment varibles
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install apk dependencies
RUN apk update
RUN apk add postgresql-dev # Needed for database connection
RUN apk add gettext # Needed for translations

# Install pip dependencies
RUN apk add --virtual build-deps gcc python3-dev musl-dev # These are needed to install pyscopg, but can be removed after
COPY Pipfile* .
RUN pip install --upgrade pip pipenv
RUN pipenv install --system
RUN apk del build-deps gcc python3-dev musl-dev

# Copy project after dependencies, so cached dependencies can be used if unchanged
COPY . .
COPY --from=navbar lucos_navbar.js lucos_eolas/templates/resources/

# Compile Translations
RUN django-admin compilemessages

# Collect static files at build time so startup.sh doesn't need to.
# Dummy values are used for env vars required at settings/model import time;
# none of these affect what collectstatic actually does.
RUN SECRET_KEY=build-time-placeholder ENVIRONMENT=production POSTGRES_PASSWORD=unused AUTH_ORIGIN=http://unused CLIENT_KEYS= SYSTEM=lucos_eolas LOGANNE_ENDPOINT=http://unused python manage.py collectstatic --noinput

CMD ["./startup.sh"]