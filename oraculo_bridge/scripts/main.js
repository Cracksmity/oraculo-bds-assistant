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

import { world, system, BlockComponentTypes } from "@minecraft/server";
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
// chatSend es una API experimental/pre-release. Requiere que la
// dependencia apunte a una versión beta de @minecraft/server Y
// que el servidor tenga habilitadas las Beta APIs.

if (world.afterEvents.chatSend) {
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
} else {
  console.warn(
    "[Oráculo Bridge] ⚠ world.afterEvents.chatSend no está disponible. " +
    "Asegúrate de que @minecraft/server apunte a una versión beta (ej. 2.10.0-beta) " +
    "y que las Beta APIs estén habilitadas en server.properties."
  );
}

// ─── Captura de Conexiones de Jugadores ────────────────────────

world.afterEvents.playerSpawn.subscribe((eventData) => {
  // initialSpawn es true solo cuando el jugador entra al servidor por primera vez,
  // no al reaparecer tras morir o cambiar de dimensión
  if (eventData.initialSpawn) {
    const playerName = eventData.player.name;
    console.warn(`[Oráculo Bridge] Jugador conectado: ${playerName}`);

    sendToBot("/event", {
      type: "player_join",
      player: playerName,
      timestamp: Date.now(),
    });
  }
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
  const chatApiReady = !!world.afterEvents.chatSend;
  console.warn(
    `[Oráculo Bridge] ✓ Behavior Pack cargado (v1.0.2). ` +
    `Chat API: ${chatApiReady ? "✓ activa" : "✗ no disponible"}. ` +
    `Biome Check: ✓ activo. ` +
    `Escuchando eventos de jugadores...`
  );
}, 100);

// ─── Sistema de Validación de Tamaño de Biomas ─────────────────
// El bot Python envía un scriptevent con las coordenadas de un bioma
// encontrado por /locate biome. Este handler samplea 8 puntos alrededor
// para estimar si el bioma es lo suficientemente grande.
//
// Comando RCON esperado:
//   scriptevent oraculo:biome_check {"x":1977,"z":2294,"biome":"swampland","requestId":"..."}
//
// Respuesta (HTTP POST a /biome-result):
//   { requestId, x, z, biome, matchCount, checkedCount, totalProbes, isLarge }

/**
 * Radio de sampling en bloques. Debe caber dentro de una tickingarea
 * de radio 4 chunks (64 bloques). El bot Python se encarga de crear
 * la tickingarea ANTES de enviar el scriptevent.
 */
const BIOME_PROBE_RADIUS = 64;

/**
 * Offsets de los 8 puntos de sampling (cruz + diagonales).
 * Las diagonales usan un radio reducido (~48 bloques) para
 * asegurar que caigan dentro de la tickingarea circular.
 */
const BIOME_PROBE_OFFSETS = [
  { dx: 0,  dz:  BIOME_PROBE_RADIUS },  // N
  { dx: 0,  dz: -BIOME_PROBE_RADIUS },  // S
  { dx:  BIOME_PROBE_RADIUS, dz: 0 },   // E
  { dx: -BIOME_PROBE_RADIUS, dz: 0 },   // W
  { dx:  48, dz:  48 },                  // NE
  { dx: -48, dz:  48 },                  // NW
  { dx:  48, dz: -48 },                  // SE
  { dx: -48, dz: -48 },                  // SW
];

/**
 * Proporción mínima de puntos que deben coincidir con el bioma
 * objetivo para considerarlo "grande". 0.5 = al menos 4 de 8.
 */
const MIN_BIOME_MATCH_RATIO = 0.5;

system.afterEvents.scriptEventReceive.subscribe((event) => {
  if (event.id !== "oraculo:biome_check") return;

  let data;
  try {
    data = JSON.parse(event.message);
  } catch (err) {
    console.warn(`[Oráculo Biome] Error parseando JSON del scriptevent: ${err}`);
    return;
  }

  const { x, z, biome, requestId } = data;
  if (x === undefined || z === undefined || !biome || !requestId) {
    console.warn(`[Oráculo Biome] Payload incompleto: ${event.message}`);
    return;
  }

  const dimension = world.getDimension("overworld");

  // Esperamos 30 ticks (1.5 seg) para que la tickingarea creada por
  // el bot Python termine de cargar los chunks en memoria.
  system.runTimeout(() => {
    let matchCount = 0;
    let checkedCount = 0;

    for (const off of BIOME_PROBE_OFFSETS) {
      const probePos = { x: x + off.dx, y: 64, z: z + off.dz };

      try {
        // Capa 2: Verificar que el chunk esté cargado antes de leer
        if (!dimension.isChunkLoaded(probePos)) {
          console.warn(
            `[Oráculo Biome] Chunk no cargado en (${probePos.x}, ${probePos.z}), saltando`
          );
          continue;
        }

        // Capa 3: getBiome con try/catch defensivo
        const biomeAt = dimension.getBiome(probePos);
        checkedCount++;

        // Comparar con y sin namespace (por si el BP devuelve con/sin prefijo)
        const biomeId = biomeAt.id;
        if (biomeId === biome || biomeId === `minecraft:${biome}`) {
          matchCount++;
        }
      } catch (err) {
        // Si getBiome falla a pesar del isChunkLoaded, no crasheamos
        console.warn(
          `[Oráculo Biome] Error en getBiome(${probePos.x}, ${probePos.z}): ${err}`
        );
      }
    }

    const isLarge =
      checkedCount > 0 && matchCount / checkedCount >= MIN_BIOME_MATCH_RATIO;

    console.warn(
      `[Oráculo Biome] Resultado para ${biome} en (${x},${z}): ` +
      `${matchCount}/${checkedCount} probes coinciden (isLarge=${isLarge})`
    );

    // Enviar resultado de vuelta al bot Python via HTTP
    sendToBot("/biome-result", {
      requestId,
      x,
      z,
      biome,
      matchCount,
      checkedCount,
      totalProbes: BIOME_PROBE_OFFSETS.length,
      isLarge,
    });
  }, 30); // 30 ticks ≈ 1.5 segundos
});

// ─── Lógica del Sistema de Ofrendas del Oráculo (Altar) ────────

// Lista negra: Ítems considerados "basura" o prohibidos (intento de farmeo masivo)
const TRASH_ITEMS = [
    "minecraft:kelp",
    "minecraft:dried_kelp",
    "minecraft:sugar_cane",
    "minecraft:bamboo"
];

// Demandas del Oráculo del día (Ley de Oferta y Demanda)
// Formato -> "ID del ítem": Valor_Base
const DAILY_REQUESTS = {
    "minecraft:diamond": 5,        
    "minecraft:gold_ingot": 3,
    "minecraft:iron_ingot": 1
};

/**
 * Verifica si un ítem está en la lista de peticiones sagradas del día.
 */
function verificarPeticionesDiarias(itemId) {
    return DAILY_REQUESTS.hasOwnProperty(itemId);
}

/**
 * Calcula los puntos aplicando la Ley de la Oferta y la Demanda (Rendimientos decrecientes).
 * Usa la raíz cuadrada de la cantidad entregada.
 */
function calcularPuntosConDecay(valorBase, cantidad) {
    return valorBase * Math.sqrt(cantidad);
}

/**
 * Procesa el inventario del cofre sagrado.
 */
function procesarCofreAltar(block, player) {
    const inventory = block.getComponent(BlockComponentTypes.Inventory);
    if (!inventory) return;

    const container = inventory.container;
    let totalPuntosNuevos = 0;
    let intentoDeFraude = false;
    let cambiosRealizados = false;

    // Mapa para agrupar cantidades del mismo ítem y evitar que el jugador esquive 
    // la penalización matemática separando los ítems en slots individuales.
    const itemsValidos = {}; 

    // 1. Recorremos todos los slots del contenedor
    for (let i = 0; i < container.size; i++) {
        const item = container.getItem(i);
        if (!item) continue; 

        const itemId = item.typeId;

        // FILTRO DE BASURA Y FRAUDE
        if (TRASH_ITEMS.includes(itemId)) {
            intentoDeFraude = true;
            container.setItem(i, undefined); // Vaciar el slot de la basura
            cambiosRealizados = true;
            continue; 
        }

        // VERIFICACIÓN DE PETICIONES DIARIAS
        if (verificarPeticionesDiarias(itemId)) {
            if (!itemsValidos[itemId]) itemsValidos[itemId] = 0;
            itemsValidos[itemId] += item.amount;
            
            container.setItem(i, undefined); // Vaciar el slot del tributo válido
            cambiosRealizados = true;
        }
    }

    // ==========================================
    // RESPUESTA Y MISTICISMO DEL ORÁCULO
    // ==========================================

    if (intentoDeFraude) {
        // Castigo divino
        player.sendMessage("§c[El Oráculo] ¿Pretendes inundar mis altares con la maleza rancia de tu mundo material? ¡Tu codicia apesta y tu ignorancia ofende!");
        player.dimension.runCommand(`summon lightning_bolt ${player.location.x} ${player.location.y} ${player.location.z}`);
        
        // Integración usando sendToBot existente en main.js
        sendToBot("/api/devocion/penalizar", {
            jugador: player.name,
            motivo: "Intento de fraude con ofrenda basura",
            puntosPenalizacion: -10 
        });
        
        return; // Detenemos el flujo aquí para no otorgar puntos
    } 
    
    if (cambiosRealizados) {
        // Cálculo de puntos usando la fórmula de Raíz Cuadrada (Decay)
        for (const [itemId, cantidad] of Object.entries(itemsValidos)) {
            const valorBase = DAILY_REQUESTS[itemId];
            totalPuntosNuevos += calcularPuntosConDecay(valorBase, cantidad);
        }

        if (totalPuntosNuevos > 0) {
            totalPuntosNuevos = Math.floor(totalPuntosNuevos); 
            
            // Mensaje místico sin revelar los puntos exactos (§d es color morado/rosa místico)
            player.sendMessage(`§d[El Oráculo] Siento la devoción en tus tributos, mortal. Tu ofrenda ha sido aceptada y tejida en el cosmos.`);

            // Integración usando sendToBot existente en main.js
            sendToBot("/api/devocion/agregar", {
                jugador: player.name,
                puntos: totalPuntosNuevos,
                ultima_ofrenda: new Date().toISOString()
            });
        }
    }
}

// ==========================================
// EVENTO: DETECCIÓN INTELIGENTE DEL ALTAR
// ==========================================

world.afterEvents.playerInteractWithBlock.subscribe((event) => {
    const { player, block } = event;

    // 1. Verificamos que sea un cofre
    if (block.typeId !== "minecraft:chest") return;

    // 2. Detección Inteligente: Comprobamos que el bloque exactamente abajo (Y-1) sea un bloque de oro
    const bloqueAbajo = block.dimension.getBlock({ x: block.x, y: block.y - 1, z: block.z });
    
    // Si no hay bloque abajo o no es un bloque de oro, entonces es un cofre normal y corriente
    if (!bloqueAbajo || bloqueAbajo.typeId !== "minecraft:gold_block") return;

    // Retrasamos el procesamiento 20 ticks (1 segundo) para que el jugador tenga 
    // tiempo de meter los ítems y cerrar la interfaz del cofre.
    system.runTimeout(() => {
        procesarCofreAltar(block, player);
    }, 20); 
});

