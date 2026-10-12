#!/bin/bash
# Vigilante del BDS: reinicia el servidor cuando pierde la señalización de NetherNet.
#
# Con transport=nethernet, el BDS escucha en TCP sobre server-port mientras está
# conectado al servicio de señalización de Microsoft. A veces esa conexión se cae
# (los sockets quedan en CLOSE-WAIT), el BDS no se reconecta y el listener
# desaparece: nadie nuevo puede entrar (InitialConnection-13) aunque el proceso
# siga vivo y el log no muestre nada. Este script detecta ese estado y reinicia
# el servidor avisando antes a los jugadores.
#
# Uso:
#   bash tools/vigilante_bds.sh            # una revisión (lo que ejecuta el cron)
#   bash tools/vigilante_bds.sh estado     # solo diagnostica, no reinicia
#   bash tools/vigilante_bds.sh instalar   # agrega la revisión cada 5 min al crontab
#   bash tools/vigilante_bds.sh desinstalar
#
# Variables opcionales: BDS_DIR (~/servidor_minecraft), BDS_SCREEN (minecraft).
set -uo pipefail
export PATH="$PATH:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SRV="${BDS_DIR:-$HOME/servidor_minecraft}"
SCREEN_NAME="${BDS_SCREEN:-minecraft}"
STATE_DIR="${VIGILANTE_STATE_DIR:-$HOME/.local/state/vigilante_bds}"
LOG_FILE="$HOME/vigilante_bds.log"
FAILS_BEFORE_RESTART=2        # revisiones fallidas seguidas antes de reiniciar
STARTUP_GRACE_SECONDS=180     # no juzgar un servidor recién arrancado
RESTART_COOLDOWN_SECONDS=900  # máximo un reinicio cada 15 min
WARNING_SECONDS=30

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
CRON_LINE="*/5 * * * * /bin/bash $SELF >> $LOG_FILE 2>&1"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

prop() {
    grep -E "^$1=" "$SRV/server.properties" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '[:space:]'
}

screen_running() { screen -ls 2>/dev/null | grep -qE "\.${SCREEN_NAME}\s"; }

bds_pid() { pgrep -x bedrock_server | head -1; }

listener_up() { ss -Htln "sport = :$1" 2>/dev/null | grep -q .; }

tell_players() {
    local text="$1"
    screen -S "$SCREEN_NAME" -p 0 -X stuff "tellraw @a {\"rawtext\":[{\"text\":\"$text\"}]}"$'\n'
}

restart_bds() {
    local port="$1"
    log "Reiniciando el BDS (aviso de ${WARNING_SECONDS}s a los jugadores)..."
    tell_players "§6[§5Oráculo§6] §dLos hilos que unen este mundo con el cosmos se han roto. El mundo renacerá en ${WARNING_SECONDS} segundos..."
    sleep "$WARNING_SECONDS"
    screen -S "$SCREEN_NAME" -p 0 -X stuff $'stop\n'

    for _ in $(seq 1 45); do
        screen_running || break
        sleep 2
    done
    if screen_running; then
        log "El BDS no respondió a 'stop' en 90s; cerrando la sesión screen."
        screen -S "$SCREEN_NAME" -X quit
        sleep 5
    fi

    screen -L -Logfile "$SRV/server.log" -dmS "$SCREEN_NAME" \
        bash -c "cd '$SRV' && LD_LIBRARY_PATH=. ./bedrock_server"
    date +%s > "$STATE_DIR/last_restart"

    for _ in $(seq 1 60); do
        if listener_up "$port"; then
            log "BDS reiniciado y escuchando en el puerto $port."
            return 0
        fi
        sleep 2
    done
    log "El BDS arrancó pero no escucha en $port tras 120s."
    return 1
}

check() {
    local dry_run="$1"
    mkdir -p "$STATE_DIR"

    local transport port pid age fails last now
    transport="$(prop transport)"
    port="$(prop server-port)"; port="${port:-19132}"

    if [ "${transport:-nethernet}" != "nethernet" ]; then
        [ "$dry_run" = 1 ] && log "transport=$transport: esta revisión solo aplica a NetherNet."
        return 0
    fi
    if ! screen_running; then
        [ "$dry_run" = 1 ] && log "No hay sesión screen '$SCREEN_NAME': el servidor está apagado a propósito."
        return 0
    fi
    pid="$(bds_pid)"
    if [ -z "$pid" ]; then
        [ "$dry_run" = 1 ] && log "La sesión screen existe pero bedrock_server no está corriendo."
        return 0
    fi
    age="$(ps -o etimes= -p "$pid" | tr -d ' ')"
    if [ "${age:-0}" -lt "$STARTUP_GRACE_SECONDS" ]; then
        [ "$dry_run" = 1 ] && log "BDS arrancado hace ${age}s; se revisa a partir de ${STARTUP_GRACE_SECONDS}s."
        return 0
    fi
    if pgrep -f "tar .*$(basename "$SRV")" >/dev/null; then
        log "Respaldo en curso; se omite la revisión."
        return 0
    fi

    if listener_up "$port"; then
        [ "$dry_run" = 1 ] && log "OK: BDS (pid $pid, ${age}s) escuchando en TCP $port; señalización activa."
        rm -f "$STATE_DIR/fails"
        return 0
    fi

    fails=$(( $(cat "$STATE_DIR/fails" 2>/dev/null || echo 0) + 1 ))
    [ "$fails" -gt "$FAILS_BEFORE_RESTART" ] && fails=$FAILS_BEFORE_RESTART
    if [ "$dry_run" = 1 ]; then
        log "FALLO: el BDS (pid $pid) no escucha en TCP $port. Probablemente perdió la señalización de NetherNet."
        return 1
    fi
    echo "$fails" > "$STATE_DIR/fails"
    log "Sin listener TCP en $port (fallo $fails/$FAILS_BEFORE_RESTART). Probable pérdida de señalización de NetherNet."
    [ "$fails" -lt "$FAILS_BEFORE_RESTART" ] && return 0

    now=$(date +%s)
    last=$(cat "$STATE_DIR/last_restart" 2>/dev/null || echo 0)
    if [ $(( now - last )) -lt "$RESTART_COOLDOWN_SECONDS" ]; then
        log "Ya se reinició hace $(( now - last ))s; se espera al cooldown de ${RESTART_COOLDOWN_SECONDS}s."
        return 0
    fi

    rm -f "$STATE_DIR/fails"
    restart_bds "$port"
}

case "${1:-}" in
    "")
        check 0 ;;
    estado)
        check 1 ;;
    instalar)
        # Se lee el crontab completo antes de reescribirlo
        current="$(crontab -l 2>/dev/null)"
        if grep -qF "$SELF" <<< "$current"; then
            echo "El vigilante ya está en el crontab."
        else
            printf '%s
%s
' "$current" "$CRON_LINE" | sed '/^$/d' | crontab -
            echo "Instalado: $CRON_LINE"
        fi ;;
    desinstalar)
        current="$(crontab -l 2>/dev/null)"
        grep -vF "$SELF" <<< "$current" | crontab -
        echo "Vigilante quitado del crontab." ;;
    *)
        echo "Uso: $0 [estado|instalar|desinstalar]"; exit 2 ;;
esac
