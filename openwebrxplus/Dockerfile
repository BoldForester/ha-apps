ARG BUILD_FROM
FROM ${BUILD_FROM}
RUN apt-get update \
 && apt-get install -y --no-install-recommends lame python3-websocket \
 && rm -rf /var/lib/apt/lists/*
COPY ha-entry.sh add-profiles.py sdr-stream.py /ha/
COPY local-bookmarks.json /ha/local-bookmarks.json
COPY init.js /usr/lib/python3/dist-packages/htdocs/plugins/receiver/init.js
COPY services.d/sdr-stream/run /etc/services.d/sdr-stream/run
RUN chmod +x /ha/ha-entry.sh /ha/sdr-stream.py /etc/services.d/sdr-stream/run
ENTRYPOINT ["/ha/ha-entry.sh"]
