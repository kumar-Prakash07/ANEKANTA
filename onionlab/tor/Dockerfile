FROM alpine:3.20
RUN apk add --no-cache tor
COPY torrc /etc/tor/torrc
COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh \
 && mkdir -p /var/lib/tor/hidden_service \
 # Created and owned here so that Docker seeds a FRESH named volume with this
 # ownership on first mount. A volume that appears root-owned at runtime cannot
 # be fixed from inside the container, because tor is unprivileged by then.
 && mkdir -p /srv/onion-addresses \
 && chown -R tor:tor /var/lib/tor /srv/onion-addresses \
 && chmod 0755 /srv/onion-addresses
USER tor
ENTRYPOINT ["/entrypoint.sh"]
