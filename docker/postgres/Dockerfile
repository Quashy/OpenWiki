FROM pgvector/pgvector:pg16 AS pgbigm-build

ARG PGBIGM_VERSION=v1.2-20250903
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        postgresql-server-dev-16 \
    && git clone --branch "${PGBIGM_VERSION}" --depth 1 https://github.com/pgbigm/pg_bigm.git /tmp/pg_bigm \
    && make -C /tmp/pg_bigm USE_PGXS=1 install \
    && rm -rf /var/lib/apt/lists/*

FROM pgvector/pgvector:pg16

COPY --from=pgbigm-build /usr/lib/postgresql/16/lib/pg_bigm.so /usr/lib/postgresql/16/lib/pg_bigm.so
COPY --from=pgbigm-build /usr/share/postgresql/16/extension/pg_bigm* /usr/share/postgresql/16/extension/
