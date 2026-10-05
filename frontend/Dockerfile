FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm install

# --- dev: Vite з автоперезавантаженням ---
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# --- збірка ---
FROM deps AS build
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
COPY . .
RUN npm run build

# --- prod: статика через nginx ---
FROM nginx:1.27-alpine AS prod
RUN apk add --no-cache openssl
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY gen-cert.sh /docker-entrypoint.d/05-gen-cert.sh
RUN chmod +x /docker-entrypoint.d/05-gen-cert.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 443
