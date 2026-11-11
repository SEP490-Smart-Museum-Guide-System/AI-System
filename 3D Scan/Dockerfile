FROM ubuntu:24.04
ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
    OPENMVS_BIN_DIR=/opt/openmvs/bin \
    PATH=/opt/venv/bin:/opt/openmvs/bin:${PATH}
WORKDIR /service
RUN apt-get update && apt-get install -y --no-install-recommends colmap libgomp1 ca-certificates curl unzip python3.12 python3.12-venv \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/openmvs/bin /usr/share/licenses/openmvs \
    && curl -fsSL https://github.com/cdcseacave/openMVS/releases/download/v2.4.0/OpenMVS_Ubuntu_x64.zip -o /tmp/openmvs.zip \
    && echo "7104ae1ddd6ca38fbca9e0e4a70b20af59e21e0b497eb7181c864fbf38ca8d00  /tmp/openmvs.zip" | sha256sum -c - \
    && unzip -q /tmp/openmvs.zip -d /opt/openmvs/bin \
    && chmod 0755 /opt/openmvs/bin/* \
    && rm /tmp/openmvs.zip
COPY THIRD_PARTY_LICENSES/OpenMVS-LICENSE ./THIRD_PARTY_LICENSES/OpenMVS-LICENSE
RUN cp THIRD_PARTY_LICENSES/OpenMVS-LICENSE /usr/share/licenses/openmvs/LICENSE
COPY requirements.txt ./requirements.txt
RUN python3.12 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt \
    && ln -s /usr/bin/python3.12 /usr/local/bin/python
COPY app ./app
RUN useradd --create-home --uid 10004 appuser && mkdir /data && chown appuser:appuser /data
USER appuser
ENV SCAN_DATA_DIR=/data
EXPOSE 8002
CMD ["/opt/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1", "--no-access-log"]
