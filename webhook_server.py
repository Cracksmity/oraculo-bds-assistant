import logging
from typing import Callable, Optional
from flask import Flask, request, jsonify

logger = logging.getLogger(__name__)


class WebhookServer:
    """
    Servidor HTTP ligero (Flask) que recibe mensajes de chat y eventos
    de jugadores desde el Behavior Pack de Minecraft Bedrock.

    Endpoints:
        POST /chat   — Recibe mensajes del chat filtrados por el Behavior Pack.
        POST /event  — Recibe eventos de conexión/desconexión de jugadores.
        GET  /health — Health check básico para verificar que el servidor está vivo.

    Cada endpoint valida el payload JSON y ejecuta el callback registrado.
    Opcionalmente, puede validar un secreto en el header 'X-Webhook-Secret'.
    """

    def __init__(
        self,
        port: int = 5050,
        chat_callback: Optional[Callable[[str, str], None]] = None,
        event_callback: Optional[Callable[[str, str], None]] = None,
        biome_result_callback: Optional[Callable[[dict], None]] = None,
        secret: Optional[str] = None,
    ) -> None:
        """
        Inicializa el servidor de webhooks.

        Args:
            port: Puerto en el que escuchará el servidor HTTP.
            chat_callback: Función que recibe (player: str, message: str) al llegar un mensaje de chat.
            event_callback: Función que recibe (event_type: str, player: str) al llegar un evento.
            biome_result_callback: Función que recibe (data: dict) con el resultado de validación
                de tamaño de bioma enviado por el Behavior Pack.
            secret: Secreto opcional para validar la autenticidad de las peticiones.
        """
        self.port: int = port
        self.chat_callback: Optional[Callable[[str, str], None]] = chat_callback
        self.event_callback: Optional[Callable[[str, str], None]] = event_callback
        self.biome_result_callback: Optional[Callable[[dict], None]] = biome_result_callback
        self.secret: Optional[str] = secret

        # Crear la aplicación Flask y reducir los logs internos de werkzeug
        self.app: Flask = Flask(__name__)
        self.app.logger.setLevel(logging.WARNING)

        werkzeug_logger = logging.getLogger("werkzeug")
        werkzeug_logger.setLevel(logging.WARNING)

        self._setup_routes()

    def _validate_secret(self) -> bool:
        """Valida el header X-Webhook-Secret si se configuró un secreto."""
        if not self.secret:
            return True
        auth = request.headers.get("X-Webhook-Secret", "")
        return auth == self.secret

    def _setup_routes(self) -> None:
        """Registra los endpoints HTTP en la aplicación Flask."""

        @self.app.route("/chat", methods=["POST"])
        def handle_chat():
            """Recibe un mensaje de chat del Behavior Pack."""
            if not self._validate_secret():
                logger.warning("Petición /chat rechazada: secreto inválido.")
                return jsonify({"error": "unauthorized"}), 403

            data = request.get_json(silent=True)
            if not data:
                return jsonify({"error": "invalid json"}), 400

            player = data.get("player", "").strip()
            message = data.get("message", "").strip()

            if not player or not message:
                return jsonify({"error": "missing fields (player, message)"}), 400

            logger.info(f"[Webhook /chat] Mensaje de '{player}': {message}")

            if self.chat_callback:
                try:
                    self.chat_callback(player, message)
                except Exception as e:
                    logger.error(
                        f"Error al procesar chat_callback para '{player}': {e}",
                        exc_info=True,
                    )

            return jsonify({"status": "ok"}), 200

        @self.app.route("/event", methods=["POST"])
        def handle_event():
            """Recibe un evento de jugador (conexión/desconexión) del Behavior Pack."""
            if not self._validate_secret():
                logger.warning("Petición /event rechazada: secreto inválido.")
                return jsonify({"error": "unauthorized"}), 403

            data = request.get_json(silent=True)
            if not data:
                return jsonify({"error": "invalid json"}), 400

            event_type = data.get("type", "").strip()
            player = data.get("player", "").strip()

            if not event_type or not player:
                return jsonify({"error": "missing fields (type, player)"}), 400

            logger.info(f"[Webhook /event] Evento '{event_type}' para '{player}'")

            if self.event_callback:
                try:
                    self.event_callback(event_type, player)
                except Exception as e:
                    logger.error(
                        f"Error al procesar event_callback '{event_type}' para '{player}': {e}",
                        exc_info=True,
                    )

            return jsonify({"status": "ok"}), 200

        @self.app.route("/biome-result", methods=["POST"])
        def handle_biome_result():
            """Recibe el resultado de validación de tamaño de bioma del Behavior Pack."""
            data = request.get_json(silent=True)
            if not data:
                return jsonify({"error": "invalid json"}), 400

            logger.info(
                f"[Webhook /biome-result] Resultado recibido: "
                f"biome={data.get('biome')}, matchCount={data.get('matchCount')}, "
                f"isLarge={data.get('isLarge')}"
            )

            if self.biome_result_callback:
                try:
                    self.biome_result_callback(data)
                except Exception as e:
                    logger.error(
                        f"Error al procesar biome_result_callback: {e}",
                        exc_info=True,
                    )

            return jsonify({"status": "ok"}), 200

        @self.app.route("/health", methods=["GET"])
        def health():
            """Health check básico."""
            return jsonify({"status": "alive", "service": "oraculo-webhook"}), 200

    def start(self) -> None:
        """
        Inicia el servidor Flask en el hilo actual (bloqueante).
        Usa host 0.0.0.0 para aceptar conexiones del localhost de la VPS.
        """
        logger.info(
            f"Iniciando Webhook Server del Oráculo en 0.0.0.0:{self.port}..."
        )
        logger.info(
            f"Endpoints disponibles: POST /chat, POST /event, POST /biome-result, GET /health"
        )
        self.app.run(
            host="0.0.0.0",
            port=self.port,
            threaded=True,
            use_reloader=False,
        )
