#!/bin/sh
# Створює самопідписаний сертифікат, якщо його ще немає
set -e

dir=/etc/nginx/certs
[ -f "$dir/cert.pem" ] && [ -f "$dir/key.pem" ] && exit 0
mkdir -p "$dir"

san="DNS:localhost,IP:127.0.0.1"
if [ -n "$PUBLIC_HOST" ] && [ "$PUBLIC_HOST" != "localhost" ]; then
    if echo "$PUBLIC_HOST" | grep -Eq '^[0-9.]+$'; then
        san="$san,IP:$PUBLIC_HOST"
    else
        san="$san,DNS:$PUBLIC_HOST"
    fi
fi

openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
    -keyout "$dir/key.pem" -out "$dir/cert.pem" \
    -subj "/CN=${PUBLIC_HOST:-localhost}" -addext "subjectAltName=$san"
echo "Створено самопідписаний сертифікат: $san"
