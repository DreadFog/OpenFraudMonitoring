FROM node:18-alpine AS client-build
WORKDIR /client
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

# fingerprint.js is served from one level up relative to app.py
# app.py resolves os.path.join(dirname(__file__), "..") => /
COPY --from=client-build /client/dist/fingerprint.js /fingerprint.js

EXPOSE 5000

CMD ["python", "app.py"]
