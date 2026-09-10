FROM python:3.12-alpine

# openssl is used only at BUILD time to bake a self-signed certificate into the
# image. Generating it at runtime would require a writable filesystem, and the
# container is deliberately read-only. The certificate is what makes TLS
# metadata (issuer, serial, validity window, public-key SHA-256) a real,
# extractable artefact for the collector rather than a hypothetical one.
RUN apk add --no-cache openssl \
 && mkdir -p /certs \
 && openssl req -x509 -newkey rsa:2048 -nodes \
      -keyout /certs/key.pem -out /certs/cert.pem -days 825 \
      -subj "/C=XX/O=Kilo Exchange/OU=infrastructure/CN=kilo-exchange.onion" \
      -addext "subjectAltName=DNS:kilo-exchange.onion,DNS:kilo.local" \
 && chmod 0444 /certs/cert.pem && chmod 0440 /certs/key.pem \
 && adduser -D -u 10001 -H -s /sbin/nologin onion \
 && chown root:10001 /certs/key.pem \
 && apk del openssl

WORKDIR /app
COPY market.py /app/market.py
USER 10001:10001
EXPOSE 8080 8443
ENTRYPOINT ["python", "-u", "/app/market.py"]
