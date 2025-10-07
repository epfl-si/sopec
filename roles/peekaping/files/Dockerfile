FROM quay-its.epfl.ch/svc0176/peekaping-web:0.0.40

USER root

RUN sed -i 's/listen.*80;/listen 8080;/g' /etc/nginx/conf.d/default.conf && \
    sed -i 's/listen.*80 default_server;/listen 8080 default_server;/g' /etc/nginx/conf.d/default.conf && \
    sed -i '/^user/d' /etc/nginx/nginx.conf && \
    mkdir -p /var/cache/nginx /var/run /var/log/nginx && \
    chmod -R 777 /usr/share/nginx/html /var/cache/nginx /var/run /var/log/nginx && \
    chgrp -R 0 /usr/share/nginx/html /var/cache/nginx /var/run /var/log/nginx && \
    chmod -R g=u /usr/share/nginx/html /var/cache/nginx /var/run /var/log/nginx

USER 1001
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
