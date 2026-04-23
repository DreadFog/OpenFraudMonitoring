FROM node:18-alpine AS client-build
WORKDIR /client
COPY client/package.json ./
RUN npm install
COPY client/ .
RUN npm run build

FROM node:18-alpine AS build

WORKDIR /app

COPY frontend/package.json ./

RUN npm install

COPY frontend/ .
COPY --from=client-build /client/dist/fingerprint.js public/fingerprint.js

RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
