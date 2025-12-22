FROM nginx:1.29.4-alpine3.23

RUN rm /etc/nginx/conf.d/*
RUN rm /usr/share/nginx/html/*

COPY routing.conf /etc/nginx/conf.d/

CMD ["nginx", "-g", "daemon off;"]
