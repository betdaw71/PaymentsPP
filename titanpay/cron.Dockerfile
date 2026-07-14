FROM alpine/curl:latest
COPY cron.sh /cron.sh
RUN chmod +x /cron.sh
CMD ["sh", "/cron.sh"]