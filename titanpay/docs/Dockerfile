FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY .well-known/security.txt /usr/share/nginx/html/.well-known/security.txt
EXPOSE 80
