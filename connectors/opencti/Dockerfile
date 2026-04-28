FROM python:3.11-slim

WORKDIR /connectors/opencti

# pycti depends on python-magic which needs the system libmagic library.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libmagic1 \
 && rm -rf /var/lib/apt/lists/*

# Install shared connector base + opencti-specific deps
COPY connectors/base/requirements.txt /connectors/base/requirements.txt
COPY connectors/opencti/requirements.txt /connectors/opencti/requirements.txt
RUN pip install --no-cache-dir -r /connectors/base/requirements.txt \
 && pip install --no-cache-dir -r /connectors/opencti/requirements.txt

# Shared library
COPY connectors/base/ /connectors/base/

# Connector source
COPY connectors/opencti/ /connectors/opencti/

CMD ["python", "main.py"]
