FROM node:20-alpine AS base
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci


FROM base AS development
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


FROM base AS build
COPY . .
# No VITE_API_BASE_URL. It was a build argument, which meant the API's address
# was inlined into the JavaScript and one image existed per environment — so
# the digest that was tested in staging was never the digest promoted to
# production. The address is read at runtime from /config.json instead, which
# a ConfigMap or a bind mount replaces.
RUN npm run build


FROM nginx:1.27-alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# The default /config.json ships in the image (same-origin /api, which is what
# nginx proxies below). A deployment that needs a different one mounts over it;
# a deployment that does not needs no configuration at all.
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
