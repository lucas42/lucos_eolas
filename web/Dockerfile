FROM nginx:1.29.8-alpine3.23
ARG VERSION
ENV VERSION=$VERSION

RUN rm /etc/nginx/conf.d/*
RUN rm /usr/share/nginx/html/*

COPY routing.conf /etc/nginx/conf.d/

CMD ["nginx", "-g", "daemon off;"]
