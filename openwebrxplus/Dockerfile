ARG BUILD_FROM
FROM ${BUILD_FROM}
COPY ha-entry.sh add-profiles.py /ha/
COPY local-bookmarks.json /ha/local-bookmarks.json
COPY init.js /usr/lib/python3/dist-packages/htdocs/plugins/receiver/init.js
RUN chmod +x /ha/ha-entry.sh
ENTRYPOINT ["/ha/ha-entry.sh"]
