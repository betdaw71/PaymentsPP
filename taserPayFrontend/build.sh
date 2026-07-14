docker build -t webappfrontend .
docker run  --restart always -d -p 80:8080 -p 443:443 -v /etc/letsencrypt:/etc/letsencrypt webappfrontend
