# Build the frontend and serve static files via nginx (US-04, design_document.md).
# The public entry point is Caddy/Auth Gateway; nginx serves static files only.

FROM node:22-alpine AS build
WORKDIR /app

# Dependencies in their own layer to cache npm install.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
