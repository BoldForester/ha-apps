ARG BUILD_FROM
FROM ${BUILD_FROM}
COPY ha-entry.sh /ha-entry.sh
RUN chmod +x /ha-entry.sh
ENTRYPOINT ["/ha-entry.sh"]
