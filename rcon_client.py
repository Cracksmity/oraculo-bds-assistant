import logging
import json
import time
import os
import subprocess
import threading
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


class RCONClient:
    """
    Cliente que envía comandos al Bedrock Dedicated Server inyectándolos
    en la consola de una sesión screen, y lee las respuestas del archivo de log.

    Bedrock Dedicated Server NO soporta RCON nativo (a diferencia de Java Edition).
    Este cliente usa `screen -X stuff` para escribir en la consola del servidor
    y parsea el archivo server.log para obtener las respuestas.

    Si el log file no contiene la salida del comando (lo cual ocurre cuando BDS
    no escribe la salida de comandos al archivo de log, o cuando hay buffering
    del sistema), se usa como fallback la captura directa del buffer de screen
    mediante `screen -X hardcopy -h`.

    Requisitos:
        - El BDS debe correr dentro de una sesión screen.
        - El BDS debe estar guardando su salida en un archivo de log (ideal, pero no estricto).
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
        self._screen_dump_path: str = os.path.join(
            tempfile.gettempdir(), f"oraculo_hardcopy_{os.getpid()}.txt"
        )

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

    def _capture_screen_lines(self) -> list:
        """
        Captura el buffer de scrollback de la sesión screen usando hardcopy -h.
        Retorna una lista de líneas no vacías.
        """
        try:
            subprocess.run(
                [
                    "screen", "-S", self.screen_name,
                    "-p", "0", "-X", "hardcopy", "-h",
                    self._screen_dump_path,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            with open(self._screen_dump_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            # Filtrar líneas vacías del padding de hardcopy
            lines = [line for line in content.split('\n') if line.strip()]
            return lines
        except FileNotFoundError:
            logger.warning("Comando 'screen' no encontrado. Captura de screen buffer no disponible.")
            return []
        except subprocess.CalledProcessError as e:
            logger.debug(f"hardcopy falló (sesión screen podría no soportar -h): {e}")
            return []
        except Exception as e:
            logger.debug(f"Error al capturar buffer de screen: {e}")
            return []
        finally:
            try:
                os.unlink(self._screen_dump_path)
            except OSError:
                pass

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

    def execute_command(self, command: str, max_wait: float = 3.0) -> str:
        """
        Ejecuta un comando en la consola del BDS y retorna la salida.

        Estrategia dual de lectura:
            1. Intenta leer la respuesta del archivo de log del servidor (rápido).
            2. Si el log no tiene salida nueva, captura el buffer de scrollback
               de screen (hardcopy -h) y calcula las líneas nuevas.

        Args:
            command: Comando de Minecraft a ejecutar (sin '/').
            max_wait: Tiempo máximo en segundos para esperar una respuesta (default: 3.0).

        Returns:
            str: La salida del comando (del log o del buffer de screen).

        Raises:
            ConnectionError: Si falla tras los reintentos.
        """
        with self._lock:
            for attempt in range(1, self.max_retries + 1):
                try:
                    # --- Snapshot ANTES del comando ---
                    log_pos = self._get_log_size()
                    pre_screen_lines = self._capture_screen_lines()

                    # --- Enviar el comando ---
                    self._send_to_screen(command)

                    # --- Polling: buscar salida en el log file ---
                    poll_interval = 0.1
                    elapsed = 0.0
                    new_output = ""
                    first_output_time = None

                    while elapsed < max_wait:
                        time.sleep(poll_interval)
                        elapsed += poll_interval
                        new_output = self._read_log_since(log_pos)

                        if new_output.strip():
                            if first_output_time is None:
                                first_output_time = elapsed
                            # Esperar un poco más para capturar respuestas multi-línea
                            if elapsed - first_output_time >= 0.3:
                                break

                    # Si el log file tuvo salida, usarla
                    if new_output.strip():
                        return new_output

                    # --- Fallback: capturar buffer de screen ---
                    if pre_screen_lines:
                        logger.debug(
                            f"Log file sin salida para '{command[:60]}'. "
                            f"Capturando buffer de screen..."
                        )
                        post_screen_lines = self._capture_screen_lines()

                        if len(post_screen_lines) > len(pre_screen_lines):
                            new_lines = post_screen_lines[len(pre_screen_lines):]
                            # Filtrar la línea del comando en sí (el echo)
                            cmd_short = command.strip()[:40]
                            filtered = [
                                line for line in new_lines
                                if cmd_short not in line
                            ]
                            screen_output = '\n'.join(filtered)
                            if screen_output.strip():
                                logger.info(
                                    f"Salida capturada del buffer de screen "
                                    f"({len(filtered)} líneas nuevas)"
                                )
                                return screen_output

                    logger.debug(
                        f"Comando '{command[:60]}' no produjo salida "
                        f"en log ni en screen tras {max_wait}s."
                    )
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
