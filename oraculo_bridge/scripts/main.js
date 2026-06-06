/**
 * Oráculo Bridge — Behavior Pack Script
 * 
 * Captura los mensajes del chat y eventos de jugadores dentro del
 * Bedrock Dedicated Server usando la Scripting API oficial, y los
 * reenvía al bot Oráculo (Python/Flask) mediante HTTP POST.
 * 
 * Dependencias:
 *   - @minecraft/server (afterEvents.chatSend, playerJoin, playerLeave)
 *   - @minecraft/server-net (http.request para POST al webhook)
 */

import { world, system } from "@minecraft/server";
import {
  http,
  HttpRequest,
  HttpRequestMethod,
  HttpHeader,
} from "@minecraft/server-net";

// ─── Configuración ─────────────────────────────────────────────
// URL base del bot Oráculo (Python Flask corriendo en la misma VPS)
const WEBHOOK_BASE_URL = "http://localhost:5050";

// Prefijo del comando que activa al Oráculo
const COMMAND_PREFIX = "!oraculo";

// ─── Utilidades ────────────────────────────────────────────────

/**
 * Envía un payload JSON al bot Oráculo via HTTP POST.
 * @param {string} endpoint - Ruta del endpoint (ej. "/chat" o "/event")
 * @param {object} data - Objeto a serializar como JSON en el body
 */
function sendToBot(endpoint, data) {
  const req = new HttpRequest(`${WEBHOOK_BASE_URL}${endpoint}`);
  req.method = HttpRequestMethod.Post;
  req.headers = [new HttpHeader("Content-Type", "application/json")];
  req.body = JSON.stringify(data);

  http
    .request(req)
    .then((response) => {
      if (response.status !== 200) {
        console.warn(
          `[Oráculo Bridge] Respuesta inesperada del bot (HTTP ${response.status}) en ${endpoint}`
        );
      }
    })
    .catch((err) => {
      console.warn(
        `[Oráculo Bridge] Error de conexión al enviar a ${endpoint}: ${err}`
      );
    });
}

// ─── Captura de Mensajes del Chat ──────────────────────────────

world.afterEvents.chatSend.subscribe((eventData) => {
  const playerName = eventData.sender.name;
  const message = eventData.message;

  // Solo reenviar mensajes que comienzan con el prefijo del Oráculo
  if (message.toLowerCase().startsWith(COMMAND_PREFIX)) {
    console.warn(
      `[Oráculo Bridge] Comando detectado de '${playerName}': ${message}`
    );

    sendToBot("/chat", {
      player: playerName,
      message: message,
      timestamp: Date.now(),
    });
  }
});

// ─── Captura de Conexiones de Jugadores ────────────────────────

world.afterEvents.playerJoin.subscribe((eventData) => {
  const playerName = eventData.playerName;
  console.warn(`[Oráculo Bridge] Jugador conectado: ${playerName}`);

  sendToBot("/event", {
    type: "player_join",
    player: playerName,
    timestamp: Date.now(),
  });
});

// ─── Captura de Desconexiones de Jugadores ─────────────────────

world.afterEvents.playerLeave.subscribe((eventData) => {
  const playerName = eventData.playerName;
  console.warn(`[Oráculo Bridge] Jugador desconectado: ${playerName}`);

  sendToBot("/event", {
    type: "player_leave",
    player: playerName,
    timestamp: Date.now(),
  });
});

// ─── Confirmación de Carga ─────────────────────────────────────

system.runTimeout(() => {
  console.warn(
    "[Oráculo Bridge] ✓ Behavior Pack cargado. Escuchando chat y eventos de jugadores..."
  );
}, 100);
