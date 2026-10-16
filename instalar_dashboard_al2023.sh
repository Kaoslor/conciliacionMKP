#!/usr/bin/env bash
# =====================================================================
# Dashboard de conciliación Marketplaces vs SAP — instalación en la instancia
# privada de Infraestructura (Amazon Linux 2023, acceso por VPN).
#
#   Instalar:    sudo bash instalar_dashboard_al2023.sh
#   Actualizar:  sudo bash instalar_dashboard_al2023.sh actualizar   (después de cambiar app.py en GitHub)
#
# Deja Streamlit como servicio (arranca solo si el servidor se reinicia).
# Como la instancia es privada y se entra por VPN, se publica directo por http en la IP interna.
# =====================================================================
set -euo pipefail

REPO_DEFAULT="https://github.com/Kaoslor/conciliacionMKP.git"
DB_HOST_DEFAULT="im-apps01.c52u0o4uwo8n.us-east-1.rds.amazonaws.com"
APP_DIR=/opt/dashboard
APP_USER=dashboard
PY=python3.11

[ "$(id -u)" -eq 0 ] || { echo "Ejecuta el script con sudo:  sudo bash $0"; exit 1; }

probar_base() {
  sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" - <<'PYCODE'
import tomllib, psycopg2
c = tomllib.load(open('/opt/dashboard/.streamlit/secrets.toml', 'rb'))['connections']['postgres']
try:
    psycopg2.connect(host=c['host'], port=c['port'], dbname=c['database'], user=c['username'],
                     password=c['password'], sslmode='require', connect_timeout=10).close()
    print('   Conexión a la base: OK')
except Exception as e:
    print('   NO conecta a la base:', str(e).strip().splitlines()[0])
    print('   -> "timeout": Infraestructura debe permitir PostgreSQL (5432) desde esta instancia en la RDS.')
    print('   -> "password authentication failed": clave mal escrita; borra')
    print('      /opt/dashboard/.streamlit/secrets.toml y vuelve a correr el script.')
PYCODE
}

if [ "${1:-}" = "actualizar" ]; then
  echo "== Actualizando desde GitHub"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
  sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
  systemctl restart dashboard
  echo "Listo: dashboard actualizado y reiniciado."
  exit 0
fi

echo "== 1/5 Paquetes del sistema"
dnf install -y -q "$PY" "$PY-pip" git || {
  echo "No se pudieron instalar paquetes: la instancia no tiene salida a internet. Pídele a Infraestructura salida (NAT) a internet."; exit 1; }

echo "== 2/5 Código del dashboard"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /sbin/nologin "$APP_USER"
if [ -d "$APP_DIR/.git" ]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
  read -rp "   URL del repositorio [$REPO_DEFAULT]: " REPO_URL
  REPO_URL=${REPO_URL:-$REPO_DEFAULT}
  mkdir -p "$APP_DIR" && chown "$APP_USER": "$APP_DIR"
  sudo -u "$APP_USER" git clone -q "$REPO_URL" "$APP_DIR"
fi

echo "== 3/5 Python y librerías (tarda 1-2 minutos)"
[ -d "$APP_DIR/venv" ] || sudo -u "$APP_USER" "$PY" -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

echo "== 4/5 Conexión a la base"
SECRETS="$APP_DIR/.streamlit/secrets.toml"
if [ ! -f "$SECRETS" ]; then
  read -rp "   Host de la base [$DB_HOST_DEFAULT]: " DBHOST; DBHOST=${DBHOST:-$DB_HOST_DEFAULT}
  read -rp "   Usuario de solo lectura [metabase_reader]: " DBUSER; DBUSER=${DBUSER:-metabase_reader}
  read -rsp "   Clave de $DBUSER (no se ve al escribir): " DBPASS; echo
  mkdir -p "$APP_DIR/.streamlit"
  DBHOST="$DBHOST" DBUSER="$DBUSER" DBPASS="$DBPASS" "$PY" - "$SECRETS" <<'PYCODE'
import json, os, sys
e = os.environ
open(sys.argv[1], 'w').write(f'''[connections.postgres]
dialect = "postgresql"
driver = "psycopg2"
host = {json.dumps(e["DBHOST"])}
port = 5432
database = "conciliacion"
username = {json.dumps(e["DBUSER"])}
password = {json.dumps(e["DBPASS"])}
query = {{ sslmode = "require", connect_timeout = "10" }}
''')
PYCODE
  chown "$APP_USER": "$SECRETS"; chmod 600 "$SECRETS"
fi
probar_base

echo "== 5/5 Servicio del dashboard"
read -rp "   Puerto web [80]: " PUERTO; PUERTO=${PUERTO:-80}
cat > /etc/systemd/system/dashboard.service <<EOF
[Unit]
Description=Dashboard conciliacion Marketplaces vs SAP (Streamlit)
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStart=$APP_DIR/venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port $PUERTO --server.headless true --browser.gatherUsageStats false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q dashboard
systemctl restart dashboard
sleep 5

IP=$(hostname -I | awk '{print $1}')
URL="http://$IP"; [ "$PUERTO" = "80" ] || URL="$URL:$PUERTO"
echo
echo "================================================================"
if systemctl is-active -q dashboard; then echo " Dashboard corriendo: $URL   (con la VPN conectada)"
else echo " El servicio no arrancó. Mira el error con: sudo journalctl -u dashboard -n 50"; fi
echo " Estado:     sudo systemctl status dashboard"
echo " Errores:    sudo journalctl -u dashboard -n 50"
echo " Actualizar: sudo bash instalar_dashboard_al2023.sh actualizar"
echo "================================================================"
