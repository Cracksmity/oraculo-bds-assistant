import os
import time
import logging
from typing import Callable

logger = logging.getLogger(__name__)

class LogMonitor:
    """
    Monitorea de forma continua (tail) un archivo de logs de Minecraft Bedrock.
    Llama a un callback cuando encuentra una línea que contiene la palabra clave configurada.
    Soporta la detección de rotación de logs (reapertura automática del archivo).
    """

    def __init__(
        self,
        file_path: str,
        callback: Callable[[str], None],
        keyword: str = "!oraculo",
        poll_interval: float = 0.5,
        read_from_end: bool = True
    ) -> None:
        """
        Inicializa el monitor de logs.

        Args:
            file_path: Ruta absoluta al archivo de logs.
            callback: Función callback que recibe la línea de log detectada.
            keyword: Palabra clave que activa el callback (ej. !oraculo).
            poll_interval: Tiempo en segundos a esperar cuando no hay nuevas líneas.
            read_from_end: Si es True, ignora el contenido existente al iniciar y solo lee nuevas líneas.
        """
        self.file_path: str = file_path
        self.callback: Callable[[str], None] = callback
        self.keyword: str = keyword
        self.poll_interval: float = poll_interval
        self.read_from_end: bool = read_from_end
        self._running: bool = False

    def start(self) -> None:
        """
        Inicia el bucle de monitoreo del archivo de log. Bloquea el hilo actual.
        Detecta si el archivo es modificado, rotado o eliminado para reconectarse.
        """
        self._running = True
        logger.info(f"Iniciando monitoreo de logs en: {self.file_path}")

        while self._running:
            if not os.path.exists(self.file_path):
                logger.warning(f"El archivo de log no existe en la ruta especificada: {self.file_path}. Esperando 5 segundos...")
                time.sleep(5)
                continue

            try:
                # Obtener metadatos del archivo para detectar rotaciones
                stat_info = os.stat(self.file_path)
                current_inode = stat_info.st_ino
                current_size = stat_info.st_size

                with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
                    if self.read_from_end:
                        # Ir al final del archivo para hacer tail real y omitir histórico anterior
                        f.seek(0, os.SEEK_END)
                        logger.info("Posicionado al final del archivo de logs (modo tail activo).")
                        self.read_from_end = False  # Solo la primera vez se salta el contenido
                    
                    while self._running:
                        line = f.readline()
                        
                        if not line:
                            # No hay nuevas líneas. Validar si el archivo rotó o se truncó.
                            if not os.path.exists(self.file_path):
                                logger.warning("El archivo de log ha dejado de existir. Intentando reabrir...")
                                break

                            try:
                                new_stat = os.stat(self.file_path)
                                # Si cambió de inodo (rotación) o su tamaño disminuyó (truncado), reabrimos
                                if new_stat.st_ino != current_inode or new_stat.st_size < f.tell():
                                    logger.info("Rotación de log detectada o archivo vaciado. Reabriendo...")
                                    break
                            except OSError:
                                # El archivo podría estar en transición de rotación
                                pass

                            time.sleep(self.poll_interval)
                            continue

                        # Procesar la línea leída
                        stripped_line = line.strip()
                        if self.keyword in stripped_line:
                            logger.info(f"Coincidencia de palabra clave detectada: {stripped_line}")
                            try:
                                self.callback(stripped_line)
                            except Exception as cb_err:
                                logger.error(f"Error al ejecutar el callback de log: {cb_err}", exc_info=True)

            except Exception as e:
                logger.error(f"Error durante el monitoreo de logs: {e}. Reintentando en 2 segundos...")
                time.sleep(2)

    def stop(self) -> None:
        """
        Detiene el bucle de monitoreo de logs.
        """
        self._running = False
        logger.info("Solicitud de detención del monitor de logs recibida.")
