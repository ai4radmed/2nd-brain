FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        squid \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/log/squid /var/run/squid \
    && chown -R proxy:proxy /var/log/squid /var/run/squid

COPY squid.conf /etc/squid/squid.conf

EXPOSE 3128

CMD ["squid", "-N", "-f", "/etc/squid/squid.conf"]
