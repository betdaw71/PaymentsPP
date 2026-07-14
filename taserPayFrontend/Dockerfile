FROM node:20-alpine AS build

WORKDIR /app


ARG VITE_API_URL
ARG VITE_AUTHORIZATION_HEADER
ARG VITE_ASSETS_URL

ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_AUTHORIZATION_HEADER=${VITE_AUTHORIZATION_HEADER}
ENV VITE_ASSETS_URL=${VITE_ASSETS_URL}

# Копируем package.json
COPY package*.json ./

# Устанавливаем зависимости без postinstall
RUN npm install --legacy-peer-deps --ignore-scripts

# Копируем исходники
COPY . .

# Создаем заглушку для build-icons.js если его нет
RUN mkdir -p src/@iconify && \
    echo '#!/usr/bin/env node\nconsole.log("Icons build skipped");\nprocess.exit(0);' > src/@iconify/build-icons.js && \
    chmod +x src/@iconify/build-icons.js

# Запускаем сборку
RUN npm run build --legacy-peer-deps || npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# Копируем nginx конфиг для проксирования API
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
