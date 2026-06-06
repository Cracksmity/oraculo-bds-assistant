import logging
import json
import time
from typing import Optional
from mcrcon import MCRcon

logger = logging.getLogger(__name__)

class RCONClient:
    """
    Clase que maneja la comunicación RCON con el servidor de Minecraft Bedrock.
    Implementa reconexión automática en caso de desconexión y métodos
    seguros para ejecutar comandos y enviar mensajes al chat usando tellraw.
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        max_retries: int = 3,
        retry_delay: float = 2.0
    ) -> None:
        """
        Inicializa el cliente de RCON.

        Args:
            host: Dirección IP o dominio del servidor de Minecraft.
            port: Puerto RCON del servidor.
            password: Contraseña de RCON.
            max_retries: Número máximo de intentos de reconexión/ejecución.
            retry_delay: Tiempo de espera (en segundos) entre reintentos.
        """
        self.host: str = host
        self.port: int = port
        self.password: str = password
        self.max_retries: int = max_retries
        self.retry_delay: float = retry_delay
        self._client: Optional[MCRcon] = None

    def connect(self) -> None:
        """
        Establece la conexión RCON con el servidor si no está conectado.
        
        Raises:
            ConnectionError: Si se agotan los intentos de conexión.
        """
        if self._client is not None:
            return

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Intentando conectar a RCON ({self.host}:{self.port}) - Intento {attempt}/{self.max_retries}")
                client = MCRcon(self.host, self.password, port=self.port)
                client.connect()
                self._client = client
                logger.info("Conexión RCON establecida con éxito.")
                return
            except Exception as e:
                logger.error(f"Error al conectar a RCON en el intento {attempt}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    raise ConnectionError(f"No se pudo establecer la conexión RCON tras {self.max_retries} intentos.") from e

    def disconnect(self) -> None:
        """
        Cierra la conexión RCON de manera segura si está abierta.
        """
        if self._client is not None:
            try:
                self._client.disconnect()
                logger.info("Conexión RCON cerrada de forma segura.")
            except Exception as e:
                logger.error(f"Error al cerrar la conexión RCON: {e}")
            finally:
                self._client = None

    def execute_command(self, command: str) -> str:
        """
        Ejecuta un comando en el servidor de Minecraft y retorna el resultado.
        En caso de desconexión, intenta reconectarse de manera automática.

        Args:
            command: Comando de Minecraft a ejecutar (sin la barra diagonal '/' inicial).

        Returns:
            str: Respuesta del servidor a la ejecución del comando.

        Raises:
            ConnectionError: Si falla la ejecución o reconexión tras los reintentos.
        """
        # Asegurar conexión
        self.connect()

        for attempt in range(1, self.max_retries + 1):
            try:
                if self._client is None:
                    raise ConnectionError("El cliente RCON no está inicializado.")
                
                # Ejecutar comando
                response = self._client.command(command)
                return response
            except Exception as e:
                logger.warning(f"Error al ejecutar comando '{command}' (intento {attempt}/{self.max_retries}): {e}")
                self.disconnect()  # Limpiar estado roto de la conexión
                
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    try:
                        self.connect()
                    except Exception as conn_err:
                        logger.error(f"Error de reconexión automático durante reintento: {conn_err}")
                else:
                    raise ConnectionError(f"No se pudo ejecutar el comando RCON tras {self.max_retries} intentos debido a errores de red o sesión.") from e
        return ""

    def send_tellraw(self, target: str, message: str) -> None:
        """
        Envía un mensaje en formato rawtext al chat del servidor usando el comando /tellraw.
        Evita problemas con comillas y caracteres especiales al codificar con JSON.

        Args:
            target: El destinatario del mensaje (ej. '@a' para todos, o el nombre de un jugador).
            message: Contenido del mensaje a enviar.
        """
        # Formatear el mensaje como JSON rawtext para Bedrock
        payload = {
            "rawtext": [
                {"text": message}
            ]
        }
        # Convertir a cadena JSON compacta sin escapar ASCII extendido
        json_payload = json.dumps(payload, ensure_ascii=False)
        command = f"tellraw {target} {json_payload}"
        
        try:
            self.execute_command(command)
        except Exception as e:
            logger.error(f"Error al enviar tellraw a {target}: {e}")
            raise
