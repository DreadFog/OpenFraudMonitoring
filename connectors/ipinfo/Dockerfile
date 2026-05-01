FROM python:3.11-slim

WORKDIR /connectors/ipinfo

# Install shared connector base + ipinfo-specific deps
COPY connectors/base/requirements.txt /connectors/base/requirements.txt
COPY connectors/ipinfo/requirements.txt /connectors/ipinfo/requirements.txt
RUN pip install --no-cache-dir -r /connectors/base/requirements.txt \
 && pip install --no-cache-dir -r /connectors/ipinfo/requirements.txt

# Shared library
COPY connectors/base/ /connectors/base/

# Connector source
COPY connectors/ipinfo/ /connectors/ipinfo/

CMD ["python", "main.py"]
