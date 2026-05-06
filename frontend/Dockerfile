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

FROM node:18-alpine AS build

WORKDIR /app

COPY frontend/package.json ./

RUN npm install

COPY frontend/ .
COPY --from=client-build /client/dist/ofm.js public/ofm.js

RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
