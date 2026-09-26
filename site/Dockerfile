FROM nginx:alpine
COPY public/ /usr/share/nginx/html/
RUN rm -f /usr/share/nginx/html/banner.html /usr/share/nginx/html/banner.css /usr/share/nginx/html/banner.js
EXPOSE 80
