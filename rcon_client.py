import logging
import json
import time
import os
import subprocess
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class RCONClient:
    """
    Cliente que envía comandos al Bedrock Dedicated Server inyectándolos
    en la consola de una sesión screen, y lee las respuestas del archivo de log.

    Bedrock Dedicated Server NO soporta RCON nativo (a diferencia de Java Edition).
    Este cliente usa `screen -X stuff` para escribir en la consola del servidor
    y parsea el archivo server.log para obtener las respuestas.

    Requisitos:
        - El BDS debe correr dentro de una sesión screen.
        - El BDS debe estar guardando su salida en un archivo de log.
    """

    def __init__(
        self,
        host: str = "",
        port: int = 0,
        password: str = "",
        max_retries: int = 3,
        retry_delay: float = 2.0,
        screen_name: str = "minecraft",
        log_file: str = "",
    ) -> None:
        """
        Inicializa el cliente de consola BDS.

        Args:
            host: (Ignorado) Se mantiene por compatibilidad.
            port: (Ignorado) Se mantiene por compatibilidad.
            password: (Ignorado) Se mantiene por compatibilidad.
            max_retries: Número máximo de reintentos al ejecutar un comando.
            retry_delay: Tiempo de espera (en segundos) entre reintentos.
            screen_name: Nombre de la sesión screen donde corre el BDS.
            log_file: Ruta al archivo de log del servidor (server.log).
        """
        self.max_retries: int = max_retries
        self.retry_delay: float = retry_delay
        self.screen_name: str = screen_name
        self.log_file: str = log_file
        self._lock: threading.Lock = threading.Lock()

    def _get_log_size(self) -> int:
        """Obtiene el tamaño actual del archivo de log."""
        try:
            return os.path.getsize(self.log_file)
        except OSError:
            return 0

    def _read_log_since(self, position: int) -> str:
        """Lee el contenido del log desde una posición dada."""
        try:
            with open(self.log_file, "r", encoding="utf-8", errors="replace") as f:
                f.seek(position)
                return f.read()
        except OSError:
            return ""

    def _send_to_screen(self, command: str) -> None:
        """Envía un comando a la sesión screen del BDS."""
        full_command = f"{command}\n"
        # El comando 'screen -X stuff' tiene un límite estricto de ~256 caracteres por llamada.
        # Para evitar el error 'non-zero exit status 1', dividimos el string en trozos más pequeños.
        chunk_size = 200
        for i in range(0, len(full_command), chunk_size):
            chunk = full_command[i:i+chunk_size]
            subprocess.run(
                [
                    "screen", "-S", self.screen_name,
                    "-p", "0", "-X", "stuff",
                    chunk,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )

    def connect(self) -> None:
        """
        Verifica que la sesión screen del BDS existe y está activa.

        Raises:
            ConnectionError: Si no se encuentra la sesión screen.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                result = subprocess.run(
                    ["screen", "-ls"], capture_output=True, text=True
                )
                if self.screen_name in result.stdout:
                    logger.info(
                        f"Sesión screen '{self.screen_name}' verificada con éxito."
                    )
                    return
                else:
                    raise ConnectionError(
                        f"No se encontró la sesión screen '{self.screen_name}'."
                    )
            except ConnectionError:
                raise
            except Exception as e:
                logger.error(
                    f"Error al verificar la sesión screen (intento {attempt}): {e}"
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    raise ConnectionError(
                        f"No se pudo verificar la sesión screen "
                        f"tras {self.max_retries} intentos."
                    ) from e

    def disconnect(self) -> None:
        """No hay estado persistente que cerrar."""
        logger.info("Cliente BDS console finalizado.")

    def execute_command(self, command: str) -> str:
        """
        Ejecuta un comando en la consola del BDS y retorna la salida del log.

        El flujo es:
            1. Marcar la posición actual del log.
            2. Inyectar el comando en la sesión screen.
            3. Esperar brevemente a que el servidor procese el comando.
            4. Leer las líneas nuevas del log como respuesta.

        Args:
            command: Comando de Minecraft a ejecutar (sin '/').

        Returns:
            str: Las nuevas líneas del log que aparecieron tras ejecutar el comando.

        Raises:
            ConnectionError: Si falla tras los reintentos.
        """
        with self._lock:
            for attempt in range(1, self.max_retries + 1):
                try:
                    log_pos = self._get_log_size()
                    self._send_to_screen(command)
                    # Esperar a que el servidor procese el comando y escriba la respuesta
                    time.sleep(0.8)
                    new_output = self._read_log_since(log_pos)
                    return new_output
                except Exception as e:
                    logger.warning(
                        f"Error al ejecutar comando '{command}' "
                        f"(intento {attempt}/{self.max_retries}): {e}"
                    )
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay)
                    else:
                        raise ConnectionError(
                            f"No se pudo ejecutar el comando "
                            f"tras {self.max_retries} intentos."
                        ) from e
        return ""

    def send_tellraw(self, target: str, message: str) -> None:
        """
        Envía un mensaje en formato rawtext al chat del servidor usando /tellraw.

        Args:
            target: Destinatario ('@a' para todos, o nombre de jugador).
            message: Contenido del mensaje a enviar.
        """
        # 1. Limpieza rigurosa de espacios y saltos de línea
        sanitized_message = message.strip()
        # Eliminar saltos de línea internos para evitar que 'screen' los interprete como la tecla 'Enter' prematuramente
        sanitized_message = sanitized_message.replace('\r', '').replace('\n', ' ')
        
        # 2. Escapado seguro de barras invertidas y comillas dobles para que no rompan la estructura JSON
        sanitized_message = sanitized_message.replace('\\', '\\\\')
        sanitized_message = sanitized_message.replace('"', '\\"')

        logger.info(f"Mensaje generado por la IA para enviar: {sanitized_message}")

        # 3. Construcción manual del JSON. 
        # A veces json.dumps añade codificaciones o secuencias de escape que la consola de Bedrock rechaza.
        json_payload = f'{{"rawtext": [{{"text": "{sanitized_message}"}}]}}'
        command = f"tellraw {target} {json_payload}"

        try:
            self.execute_command(command)
        except Exception as e:
            logger.error(f"Error al enviar tellraw a {target}: {e}")
            raise
