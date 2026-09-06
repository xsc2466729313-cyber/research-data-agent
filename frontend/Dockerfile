FROM nginx:1.27-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/index.html /usr/share/nginx/html/index.html
COPY frontend/styles.css /usr/share/nginx/html/styles.css
COPY frontend/app.js /usr/share/nginx/html/app.js
COPY frontend/astronomy.js /usr/share/nginx/html/astronomy.js
COPY frontend/agent-architecture-evidence-driven.svg /usr/share/nginx/html/agent-architecture-evidence-driven.svg

EXPOSE 80
