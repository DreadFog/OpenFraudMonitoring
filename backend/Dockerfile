FROM node:18-alpine AS client-build
ARG OFM_SERVER_URL=""
ARG FPSCANNER_KEY="dev-key"
ARG OFM_DEBUG="false"
ENV OFM_SERVER_URL=${OFM_SERVER_URL}
ENV FPSCANNER_KEY=${FPSCANNER_KEY}
ENV OFM_DEBUG=${OFM_DEBUG}
WORKDIR /client
COPY fpscanner/ /fpscanner/
COPY client/package.json ./
RUN npm install
COPY client/ .
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend modules
COPY backend/ ./

# ofm.js is served from one level up relative to app.py
# app.py resolves os.path.join(dirname(__file__), "..") => /
COPY --from=client-build /client/dist/ofm.js /ofm.js

EXPOSE 5000

CMD ["python", "app.py"]
