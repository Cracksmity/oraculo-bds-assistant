import json
import logging
import threading
from typing import Callable, Optional

from log_monitor import LogMonitor

logger = logging.getLogger(__name__)

# Marcador que el Behavior Pack antepone a cada mensaje en la consola del BDS.
IPC_MARKER = "ORACULO_IPC::"


class ConsoleBridge:
    """
    Recibe los mensajes del Behavior Pack leyendo la consola del BDS (server.log).

    Reemplaza al WebhookServer: @minecraft/server-net solo existe como API beta y,
    desde BDS 1.26.30, los mundos con Beta APIs activas no dejan conectar jugadores.
    El Behavior Pack escribe líneas con el formato:
        ORACULO_IPC::{"endpoint": "/chat", "data": {...}}
    y este puente las despacha a los mismos callbacks que usaba el webhook.

    Endpoints:
        /chat                     — data: {player, message}
        /event                    — data: {type, player}
        /biome-result             — data: resultado del sampling de biomas
        /api/devocion/agregar     — data: {jugador, puntos}
        /api/devocion/penalizar   — data: {jugador, puntosPenalizacion}
    """

    def __init__(
        self,
        log_file: str,
        chat_callback: Optional[Callable[[str, str], None]] = None,
        event_callback: Optional[Callable[[str, str], None]] = None,
        biome_result_callback: Optional[Callable[[dict], None]] = None,
        devotion_callback: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        self.chat_callback = chat_callback
        self.event_callback = event_callback
        self.biome_result_callback = biome_result_callback
        self.devotion_callback = devotion_callback
        self._monitor = LogMonitor(
            file_path=log_file,
            callback=self._handle_line,
            keyword=IPC_MARKER,
        )

    def _run_async(self, name: str, func: Callable, *args) -> None:
        """
        Ejecuta un callback en su propio hilo. Necesario porque procesar un chat
        puede esperar respuestas del Behavior Pack (p. ej. /biome-result) que
        llegan por este mismo lector de logs.
        """
        def runner() -> None:
            try:
                func(*args)
            except Exception as e:
                logger.error(f"Error al procesar '{name}': {e}", exc_info=True)

        threading.Thread(target=runner, name=f"bridge-{name}", daemon=True).start()

    def _handle_line(self, line: str) -> None:
        """Extrae y despacha el payload JSON de una línea de consola."""
        # Se usa la primera aparición: el texto del jugador va escapado dentro del JSON.
        raw = line[line.find(IPC_MARKER) + len(IPC_MARKER):]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"Línea IPC con JSON inválido ({e}): {raw[:200]}")
            return

        endpoint = payload.get("endpoint", "")
        data = payload.get("data") or {}

        if endpoint == "/chat":
            player = str(data.get("player", "")).strip()
            message = str(data.get("message", "")).strip()
            if not player or not message:
                logger.warning(f"[Bridge /chat] Payload incompleto: {data}")
                return
            logger.info(f"[Bridge /chat] Mensaje de '{player}': {message}")
            if self.chat_callback:
                self._run_async("chat", self.chat_callback, player, message)

        elif endpoint == "/event":
            event_type = str(data.get("type", "")).strip()
            player = str(data.get("player", "")).strip()
            if not event_type or not player:
                logger.warning(f"[Bridge /event] Payload incompleto: {data}")
                return
            logger.info(f"[Bridge /event] Evento '{event_type}' para '{player}'")
            if self.event_callback:
                self._run_async("event", self.event_callback, event_type, player)

        elif endpoint == "/biome-result":
            logger.info(
                f"[Bridge /biome-result] biome={data.get('biome')}, "
                f"matchCount={data.get('matchCount')}, isLarge={data.get('isLarge')}"
            )
            if self.biome_result_callback:
                self.biome_result_callback(data)

        elif endpoint in ("/api/devocion/agregar", "/api/devocion/penalizar"):
            player = str(data.get("jugador", "")).strip()
            key = "puntos" if endpoint.endswith("agregar") else "puntosPenalizacion"
            try:
                delta = int(data.get(key, 0))
            except (TypeError, ValueError):
                logger.warning(f"[Bridge {endpoint}] Puntos inválidos: {data}")
                return
            if not player or delta == 0:
                return
            logger.info(f"[Bridge {endpoint}] '{player}' {delta:+d} puntos de devoción")
            if self.devotion_callback:
                self._run_async("devocion", self.devotion_callback, player, delta)

        else:
            logger.warning(f"[Bridge] Endpoint desconocido: {endpoint}")

    def start(self) -> None:
        """Inicia el tail del server.log (bloqueante)."""
        logger.info(f"Puente de consola escuchando mensaje '{IPC_MARKER}' en el server.log")
        self._monitor.start()

    def stop(self) -> None:
        self._monitor.stop()
