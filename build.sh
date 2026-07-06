#!/bin/sh
# Build script — corre en el HOST antes de docker build
# Necesita acceso a /workspace/proyectos/data/predictions_mx.db

set -e

cd "$(dirname "$0")"

echo "==> Building Next.js standalone (en host, con acceso a BD)..."
npx next build

echo "==> Verificando output..."
if [ ! -f .next/standalone/server.js ]; then
  echo "ERROR: .next/standalone/server.js no existe. Build falló."
  exit 1
fi

echo "==> Build OK. Ahora puedes correr:"
echo "    docker build -t quiniela-frontend:v1 ."