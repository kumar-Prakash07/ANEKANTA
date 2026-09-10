# ANEKANTA analyst application.
#
# Two stages so the runtime image does not carry a compiler toolchain. The
# heavy dependency is PyTorch; the CPU-only wheel index is used deliberately,
# because the default index pulls CUDA libraries that add roughly two
# gigabytes and are useless here -- the author-embedding model is a two-layer
# projection that trains in seconds on a CPU.

FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY requirements.txt .
# CPU-only torch first, then everything else from PyPI *with torch filtered out
# of the list*. Without that filter the second install re-resolves torch from
# the default index, silently replaces the CPU wheel with the CUDA build, and
# drags in sixteen nvidia-* packages and ~6 GB that never execute here: the
# author-embedding model is a two-layer projection that trains on CPU in
# seconds.
RUN grep -viE '^[[:space:]]*torch' requirements.txt > /tmp/req-no-torch.txt \
 && pip install --prefix=/install \
      --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --prefix=/install -r /tmp/req-no-torch.txt


FROM python:3.12-slim

# curl is present only for the container health check.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10002 --shell /usr/sbin/nologin anveshak

COPY --from=build /install /usr/local

WORKDIR /app
COPY anveshak/ /app/anveshak/
COPY run.py /app/run.py
COPY onionlab/ground_truth.json /app/onionlab/ground_truth.json

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ANEKANTA_TOR=tor:9050

USER 10002:10002
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/live/status > /dev/null || exit 1

# The dashboard builds the benchmark on startup, which takes a couple of
# minutes; the health check's start period allows for it.
ENTRYPOINT ["python", "run.py"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
