FROM lucas42/lucos_navbar:2.1.63 AS navbar

FROM python:3.15.0a8-alpine AS app
ARG VERSION
ENV VERSION=$VERSION

# set working directory
WORKDIR /usr/src/app

# set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install apk dependencies
RUN apk update
RUN apk add postgresql-dev # Needed for database connection
RUN apk add gettext # Needed for translations

# Install pip dependencies
RUN apk add --virtual build-deps gcc python3-dev musl-dev # These are needed to install pyscopg, but can be removed after
COPY app/Pipfile* .
RUN pip install --upgrade pip pipenv
RUN pipenv install --system
RUN apk del build-deps gcc python3-dev musl-dev

# Copy project after dependencies, so cached dependencies can be used if unchanged
COPY app/ .
COPY --from=navbar lucos_navbar.js lucos_eolas/templates/resources/

# Compile Translations
RUN django-admin compilemessages

# Collect static files at build time. The web stage copies from here via COPY --from=app,
# so no shared volume or runtime copy step is needed.
# Uses a minimal settings file to avoid env var requirements at build time.
RUN python manage.py collectstatic --noinput --settings=lucos_eolas.settings_collectstatic

CMD ["./startup.sh"]

FROM nginx:1.29.8-alpine3.23 AS web
ARG VERSION
ENV VERSION=$VERSION

RUN rm /etc/nginx/conf.d/*
RUN rm /usr/share/nginx/html/*

COPY web/routing.conf /etc/nginx/conf.d/
COPY --from=app /usr/src/app/lucos_eolas/static /usr/share/nginx/html/resources

CMD ["nginx", "-g", "daemon off;"]
