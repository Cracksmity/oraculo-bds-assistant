import os
import re
import sys
import math
import time
import random
import json
import logging
from typing import Optional, Dict, List
from dotenv import load_dotenv

from rcon_client import RCONClient
from log_monitor import LogMonitor
from webhook_server import WebhookServer
from ai_handler import AIHandler

# Configurar el sistema de logs
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")

# Cargar variables de entorno
load_dotenv()

# Variables de configuración
RCON_HOST = os.getenv("RCON_HOST", "127.0.0.1")
RCON_PORT_STR = os.getenv("RCON_PORT", "19132")
RCON_PASS = os.getenv("RCON_PASS")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH")
COMMAND_KEYWORD = os.getenv("COMMAND_KEYWORD", "!oraculo")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
RESPONSE_TARGET_TEMPLATE = os.getenv("RESPONSE_TARGET", "@a")

# Configuración del Webhook Server (puente con Behavior Pack)
WEBHOOK_PORT_STR = os.getenv("WEBHOOK_PORT", "5050")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

COOLDOWN_SECONDS_STR = os.getenv("COOLDOWN_SECONDS", "60")
REVEAL_EXACT_COORDS_STR = os.getenv("REVEAL_EXACT_COORDS", "False")

# Lista de jugadores con Favor Divino
DIVINE_FAVOR_PLAYERS_RAW = os.getenv("DIVINE_FAVOR_PLAYERS", "")
DIVINE_FAVOR_PLAYERS: List[str] = [
    p.strip() for p in DIVINE_FAVOR_PLAYERS_RAW.split(",") if p.strip()
]

# Validaciones iniciales
if not RCON_PASS:
    logger.critical("Falta la variable RCON_PASS en el archivo .env. Saliendo...")
    sys.exit(1)
if not OPENAI_API_KEY:
    logger.critical("Falta la variable OPENAI_API_KEY en el archivo .env. Saliendo...")
    sys.exit(1)
if not LOG_FILE_PATH:
    logger.warning("LOG_FILE_PATH no configurado. El monitor de logs estará desactivado (solo se usará el webhook).")

try:
    RCON_PORT = int(RCON_PORT_STR)
except ValueError:
    logger.critical(f"El puerto RCON '{RCON_PORT_STR}' no es un número válido. Saliendo...")
    sys.exit(1)

try:
    COOLDOWN_SECONDS = int(COOLDOWN_SECONDS_STR)
except ValueError:
    logger.warning(f"COOLDOWN_SECONDS inválido '{COOLDOWN_SECONDS_STR}', se usará por defecto 60 segundos.")
    COOLDOWN_SECONDS = 60

REVEAL_EXACT_COORDS = REVEAL_EXACT_COORDS_STR.strip().lower() in ("true", "1", "yes")

try:
    WEBHOOK_PORT = int(WEBHOOK_PORT_STR)
except ValueError:
    logger.warning(f"WEBHOOK_PORT inválido '{WEBHOOK_PORT_STR}', se usará por defecto 5050.")
    WEBHOOK_PORT = 5050

# Diccionarios en memoria
last_query_times: Dict[str, float] = {}
failed_requests_count: Dict[str, int] = {}
punishment_count: Dict[str, int] = {}

# Estado del acertijo activo
active_riddle: Optional[dict] = None
active_riddle_time: float = 0.0

# Ira divina global
global_wrath: int = 0

# Inicializar servicios
logger.info("Inicializando clientes y servicios...")
rcon_client = RCONClient(host=RCON_HOST, port=RCON_PORT, password=RCON_PASS)
ai_handler = AIHandler(api_key=OPENAI_API_KEY, model=OPENAI_MODEL)

# ---- SISTEMA DE DEVOCIÓN DINÁMICA ----
DEVOCION_FILE = "devocion.json"

def load_devocion() -> dict:
    if not os.path.exists(DEVOCION_FILE):
        db = {}
        for player in DIVINE_FAVOR_PLAYERS:
            db[player] = {"puntos": 500, "rango": "Predilecto", "ultima_ofrenda": 0.0}
        save_devocion(db)
        return db
    try:
        with open(DEVOCION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error al cargar devocion.json: {e}")
        return {}

def save_devocion(db: dict) -> None:
    try:
        with open(DEVOCION_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error al guardar devocion.json: {e}")

def get_player_devocion_data(player: str) -> dict:
    db = load_devocion()
    if player not in db:
        puntos = 10
        rango = "Creyente"
        if player in DIVINE_FAVOR_PLAYERS:
            puntos = 500
            rango = "Predilecto"
        db[player] = {
            "puntos": puntos,
            "rango": rango,
            "ultima_ofrenda": 0.0
        }
        save_devocion(db)
    return db[player]

def update_player_devocion(player: str, delta: int) -> dict:
    db = load_devocion()
    if player not in db:
        puntos = 10
        rango = "Creyente"
        if player in DIVINE_FAVOR_PLAYERS:
            puntos = 500
            rango = "Predilecto"
        db[player] = {
            "puntos": puntos,
            "rango": rango,
            "ultima_ofrenda": 0.0
        }
    
    data = db[player]
    nuevos_puntos = data["puntos"] + delta
    
    if player in DIVINE_FAVOR_PLAYERS:
        nuevos_puntos = max(200, nuevos_puntos)  # Suelo VIP de 200 puntos
    else:
        nuevos_puntos = max(0, nuevos_puntos)
        
    data["puntos"] = nuevos_puntos
    
    if nuevos_puntos >= 400:
        data["rango"] = "Predilecto"
    elif nuevos_puntos >= 150:
        data["rango"] = "Devoto"
    elif nuevos_puntos >= 50:
        data["rango"] = "Creyente"
    elif nuevos_puntos >= 15:
        data["rango"] = "Dudoso"
    else:
        data["rango"] = "Hereje"
        
    db[player] = data
    save_devocion(db)
    return data

# ---- SISTEMA DE IRA DIVINA GLOBAL ----
def increase_wrath(amount: int) -> None:
    global global_wrath
    global_wrath += amount
    logger.info(f"Ira colectiva global incrementada en {amount}. Total actual: {global_wrath}/100")
    if global_wrath >= 100:
        global_wrath = 0
        trigger_wrath_event()

def trigger_wrath_event() -> None:
    logger.warning("¡Desatando la IRA DIVINA global en el servidor!")
    message = (
        "§6[§5Oráculo§6] §4¡La paciencia cósmica se ha agotado! "
        "La ira de los antiguos dioses cae sobre el reino. ¡Sálvese quien pueda!"
    )
    try:
        rcon_client.send_tellraw("@a", message)
    except Exception as e:
        logger.error(f"Error al enviar tellraw de ira divina: {e}")
        
    try:
        rcon_client.execute_command("weather thunder")
        rcon_client.execute_command("time set night")
        rcon_client.execute_command("execute at @a run playsound ambient.weather.thunder @s")
        rcon_client.execute_command("execute at @a run particle minecraft:large_explosion ~ ~1 ~")
        # Convocar phantoms y vexes a todos los jugadores excepto Geniustree y Woozidan123
        rcon_client.execute_command("execute at @a[name=!Geniustree,name=!Woozidan123] run summon phantom ~ ~10 ~")
        rcon_client.execute_command("execute at @a[name=!Geniustree,name=!Woozidan123] run summon vex ~ ~2 ~")
    except Exception as e:
        logger.error(f"Error al desatar ira divina en RCON: {e}")

# Expresiones regulares
# Detección del chat del jugador y extracción de la consulta completa
CHAT_EXTRACT_PATTERN = re.compile(
    rf"(?:<(?P<player1>[^>]+)>\s*|(?P<player2>[a-zA-Z0-9_ ]+):\s*){re.escape(COMMAND_KEYWORD)}(?:\s+(?P<query>.*))?"
)

# Coordenadas numéricas generales (locate de estructura)
COORDS_PATTERN = re.compile(r"(-?\d+)\s*,\s*(~|-?\d+)\s*,\s*(-?\d+)")

# Coordenadas del jugador (teleport)
PLAYER_COORDS_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")

# Lista de palabras consideradas insultos al Oráculo
INSULTS = [
    "tonto", "tonta", "estupido", "estúpido", "estupida", "estúpida", "idiota", "puto", 
    "puta", "mierda", "basura", "pendejo", "culero", "culera", "maricon", "cabron", 
    "cabrón", "feo", "fea", "inutil", "inútil", "inservible", "estupidez", "imbecil", "imbécil"
]

# Tabla de probabilidades base para obtención de ítems
ITEM_RARITIES: Dict[str, float] = {
    # Legendario (base 2%)
    "netherite_ingot": 0.02, "elytra": 0.02, "enchanted_golden_apple": 0.02,
    "totem_of_undying": 0.02, "beacon": 0.01, "diamond_block": 0.02,
    
    # Raro (base 15%)
    "diamond": 0.15, "emerald": 0.20, "golden_apple": 0.15, "ender_pearl": 0.20,
    
    # Poco común (base 50%)
    "iron_ingot": 0.50, "gold_ingot": 0.50, "coal": 0.65, "bread": 0.75,
    
    # Común (base 85%)
    "stone": 0.85, "cobblestone": 0.85, "torch": 0.90, "dirt": 0.95
}

def get_item_probability(item: str) -> float:
    """Retorna la probabilidad base de obtener un ítem, usando clasificación inteligente por palabra clave si no está en la tabla."""
    item = item.lower()
    if item in ITEM_RARITIES:
        return ITEM_RARITIES[item]
    
    # Clasificación por patrones en el nombre
    if any(k in item for k in ["netherite", "elytra", "totem", "beacon", "shulker", "star", "dragon"]):
        return 0.02
    if any(k in item for k in ["diamond", "emerald", "gold", "pearl", "tnt", "obsidian", "crystal", "sword"]):
        return 0.15
    if any(k in item for k in ["iron", "chainmail", "redstone", "lapis", "copper", "shears", "shield", "bow", "arrow"]):
        return 0.50
    return 0.70

def check_for_insults(text: str) -> bool:
    """Verifica si la consulta contiene algún insulto en la lista."""
    text_lower = text.lower()
    for insult in INSULTS:
        pattern = rf"\b{re.escape(insult)}\b"
        if re.search(pattern, text_lower):
            return True
    return False

def get_direction_and_distance(p_x: float, p_z: float, s_x: float, s_z: float) -> tuple[float, str]:
    """Calcula la distancia 2D y dirección cardinal de jugador a estructura."""
    dx = s_x - p_x
    dz = s_z - p_z
    distance = math.sqrt(dx**2 + dz**2)

    angle = math.degrees(math.atan2(dz, dx))
    if angle < 0:
        angle += 360

    if 22.5 <= angle < 67.5:
        direction = "Sureste"
    elif 67.5 <= angle < 112.5:
        direction = "Sur"
    elif 112.5 <= angle < 157.5:
        direction = "Suroeste"
    elif 157.5 <= angle < 202.5:
        direction = "Oeste"
    elif 202.5 <= angle < 247.5:
        direction = "Noroeste"
    elif 247.5 <= angle < 292.5:
        direction = "Norte"
    elif 292.5 <= angle < 337.5:
        direction = "Noreste"
    else:
        direction = "Este"

    return distance, direction

def check_cooldown(player: str) -> Optional[int]:
    """Calcula el cooldown restante considerando la devoción del jugador."""
    current_time = time.time()
    data = get_player_devocion_data(player)
    puntos = data["puntos"]
    
    # A más puntos, menor cooldown (desde COOLDOWN_SECONDS hasta 1/5 del mismo con 500 puntos)
    factor = 1.0 - 0.8 * min(1.0, puntos / 500.0)
    limit = max(5, int(COOLDOWN_SECONDS * factor))
        
    if player in last_query_times:
        elapsed = current_time - last_query_times[player]
        if elapsed < limit:
            return int(limit - elapsed)
    return None

def execute_smite(player: str, reason_outcome: str, target_item: str = "") -> None:
    """Fulmina al jugador con un rayo divino (smite) y lo elimina del juego."""
    logger.warning(f"¡SMITE disparado para el jugador '{player}' debido a: {reason_outcome}!")
    
    # Restar devoción e incrementar ira colectiva
    if reason_outcome == "insult_smited":
        nueva_data = update_player_devocion(player, -150)
        increase_wrath(25)
    else:
        nueva_data = update_player_devocion(player, -100)
        increase_wrath(20)

    # 1. Ejecutar RCON para invocar rayo y matar al jugador
    try:
        rcon_client.execute_command(f"execute at \"{player}\" run playsound mob.elder_guardian.curse @a")
        rcon_client.execute_command(f"execute at \"{player}\" run summon lightning_bolt")
        rcon_client.execute_command(f"kill \"{player}\"")
    except Exception as e:
        logger.error(f"Error al ejecutar comandos RCON de smite: {e}")

    # 2. Obtener respuesta poética del LLM
    mystical_message = ai_handler.generate_item_response(
        player_name=player,
        item=target_item,
        outcome=reason_outcome,
        devocion_rango=nueva_data["rango"]
    )
    final_message = f"§6[§5Oráculo§6] §c{mystical_message} §7(Devoción: {nueva_data['puntos']}, Rango: {nueva_data['rango']})"

    # 3. Anunciar globalmente a todos los jugadores
    try:
        rcon_client.send_tellraw("@a", final_message)
    except Exception as e:
        logger.error(f"Error al enviar mensaje global de smite: {e}")

def process_item_request(player: str, item: str) -> None:
    """Maneja la lógica de petición de ítems con probabilidades, cooldown, codicia, castigos y devoción."""
    # 1. Verificar Cooldown
    remaining = check_cooldown(player)
    if remaining is not None:
        logger.info(f"Jugador '{player}' está en cooldown para petición de ítem. Restante: {remaining}s")
        try:
            rcon_client.send_tellraw(
                player,
                f"§6[§5Oráculo§6] §cLas estrellas aún se están alineando. Espera {remaining} segundos."
            )
        except Exception:
            pass
        return

    # Registrar tiempo de la consulta
    last_query_times[player] = time.time()
    
    # Obtener devoción del jugador
    devocion_data = get_player_devocion_data(player)
    puntos = devocion_data["puntos"]

    # 2. Calcular probabilidades basadas en devoción (de 1x a 5x multiplicador)
    base_prob = get_item_probability(item)
    mult = 1.0 + 4.0 * min(1.0, puntos / 500.0)
    final_prob = min(1.0, base_prob * mult)

    roll = random.random()
    logger.info(f"Petición de ítem '{item}' por '{player}'. Probabilidad: {final_prob:.2%}, Dado tirado: {roll:.2%}")

    # 3. Resolución: Éxito
    if roll <= final_prob:
        failed_requests_count[player] = 0  # Resetear codicia
        logger.info(f"¡Éxito! Concediendo '{item}' a '{player}'")
        
        # Dar ítem
        try:
            rcon_client.execute_command(f"give \"{player}\" {item} 1")
            rcon_client.execute_command(f"execute at \"{player}\" run playsound random.levelup @a")
            rcon_client.execute_command(f"execute at \"{player}\" run particle minecraft:totem_particle ~ ~1 ~")
        except Exception as e:
            logger.error(f"Error al dar el ítem vía RCON: {e}")

        # Otorgar devoción por buena fe
        nueva_data = update_player_devocion(player, 10)

        # Generar respuesta IA
        response = ai_handler.generate_item_response(
            player_name=player, item=item, outcome="success", devocion_rango=nueva_data["rango"]
        )
        final_message = f"§6[§5Oráculo§6] §a{response} §e(+10 Devoción, Rango: {nueva_data['rango']})"
        
        try:
            rcon_client.send_tellraw("@a", final_message)
        except Exception:
            pass

    # 4. Resolución: Fallo (Codicia)
    else:
        failed_requests_count[player] = failed_requests_count.get(player, 0) + 1
        current_failed = failed_requests_count[player]
        logger.info(f"Fallo. Conteo de codicia actual para '{player}': {current_failed}/3")

        # 4.1. Castigo corporal (3er fallo consecutivo)
        if current_failed >= 3:
            failed_requests_count[player] = 0  # Resetear codicia
            
            # Incrementar contador de castigos
            punishment_count[player] = punishment_count.get(player, 0) + 1
            current_punishments = punishment_count[player]
            logger.warning(f"Castigos acumulados para '{player}': {current_punishments}/3")

            # Fulminar directamente en el 3er castigo
            if current_punishments >= 3:
                punishment_count[player] = 0  # Resetear castigos
                execute_smite(player, "smited", item)
            else:
                # Quitar devoción e incrementar ira global
                nueva_data = update_player_devocion(player, -20)
                increase_wrath(10)
                
                # Aplicar efecto adverso aleatorio
                effect_choices = [
                    ("blindness", "blindness 15 1 true", "Ceguera (15s)"),
                    ("poison", "poison 10 0 true", "Veneno (10s)"),
                    ("slowness", "slowness 20 1 true", "Lentitud (20s)"),
                    ("nausea", "nausea 15 1 true", "Náuseas (15s)")
                ]
                effect_key, effect_cmd_args, effect_name = random.choice(effect_choices)
                logger.warning(f"Aplicando castigo '{effect_name}' al jugador '{player}'")

                try:
                    rcon_client.execute_command(f"execute at \"{player}\" run playsound mob.elder_guardian.curse @s")
                    rcon_client.execute_command(f"effect \"{player}\" {effect_cmd_args}")
                except Exception as e:
                    logger.error(f"Error al aplicar el efecto RCON: {e}")

                response = ai_handler.generate_item_response(
                    player_name=player, item=item, outcome="punished", effect=effect_name, devocion_rango=nueva_data["rango"]
                )
                final_message = f"§6[§5Oráculo§6] §c{response} §e(-20 Devoción, Rango: {nueva_data['rango']})"
                try:
                    rcon_client.send_tellraw("@a", final_message)
                except Exception:
                    pass

        # 4.2. Fallo normal
        else:
            # Quitar un poco de devoción e incrementar ira global
            nueva_data = update_player_devocion(player, -5)
            increase_wrath(2)
            
            response = ai_handler.generate_item_response(
                player_name=player, item=item, outcome="fail", devocion_rango=nueva_data["rango"]
            )
            final_message = f"§6[§5Oráculo§6] §d{response} §e(-5 Devoción, Rango: {nueva_data['rango']})"
            try:
                rcon_client.send_tellraw("@a", final_message)
            except Exception:
                pass

def process_command(player: str, structure: str) -> None:
    """Orquesta la localización de estructuras."""
    remaining = check_cooldown(player)
    if remaining is not None:
        logger.info(f"Jugador '{player}' en cooldown para locate. Restante: {remaining}s")
        try:
            rcon_client.send_tellraw(
                player,
                f"§6[§5Oráculo§6] §cLas energías cósmicas aún no se alinean. Espera {remaining} segundos."
            )
        except Exception:
            pass
        return

    last_query_times[player] = time.time()
    logger.info(f"Procesando solicitud de '{player}' para buscar '{structure}'")

    devocion_data = get_player_devocion_data(player)
    
    p_x, p_z = None, None
    s_x, s_z = None, None
    distance, direction = None, None

    # Teleport para posición de jugador
    try:
        tp_response = rcon_client.execute_command(f"teleport \"{player}\" ~ ~ ~")
        match_p_coords = PLAYER_COORDS_PATTERN.search(tp_response)
        if match_p_coords:
            p_x = float(match_p_coords.group(1))
            p_z = float(match_p_coords.group(3))
    except Exception as e:
        logger.warning(f"No se pudo obtener la posición del jugador '{player}': {e}")

    # Locate estructura
    rcon_response = ""
    try:
        cmd = f"execute as \"{player}\" at @s run locate structure {structure}"
        rcon_response = rcon_client.execute_command(cmd)
    except Exception as e:
        logger.error(f"Error al ejecutar locate en RCON: {e}")
        try:
            rcon_client.send_tellraw(
                "@a",
                "§6[§5Oráculo§6] §cLos astros tiemblan y la conexión espiritual con el servidor se ha quebrado."
            )
        except Exception:
            pass
        return

    # Extraer coordenadas de estructura
    match_coords = COORDS_PATTERN.search(rcon_response)
    if match_coords:
        s_x_str = match_coords.group(1)
        s_y_str = match_coords.group(2)
        s_z_str = match_coords.group(3)
        try:
            s_x = float(s_x_str)
            s_z = float(s_z_str)
        except ValueError:
            pass

    # Calcular rumbo/distancia
    if p_x is not None and p_z is not None and s_x is not None and s_z is not None:
        distance, direction = get_direction_and_distance(p_x, p_z, s_x, s_z)

    # Otorgar o restar devoción según si se encontró la estructura
    if match_coords:
        nueva_data = update_player_devocion(player, 2)
        try:
            rcon_client.execute_command(f"execute at \"{player}\" run playsound block.respawn_anchor.charge @s")
        except Exception:
            pass
    else:
        nueva_data = update_player_devocion(player, -2)
        increase_wrath(1)

    # Generar respuesta
    x_arg = s_x_str if (REVEAL_EXACT_COORDS and match_coords) else None
    y_arg = s_y_str if (REVEAL_EXACT_COORDS and match_coords) else None
    z_arg = s_z_str if (REVEAL_EXACT_COORDS and match_coords) else None

    mystical_message = ai_handler.generate_response(
        player_name=player,
        structure=structure,
        x=x_arg,
        y=y_arg,
        z=z_arg,
        distance=distance,
        direction=direction,
        reveal_exact_coords=REVEAL_EXACT_COORDS,
        devocion_rango=nueva_data["rango"]
    )

    final_message = f"§6[§5Oráculo§6] §d{mystical_message} §e(Rango: {nueva_data['rango']})"

    if "{player}" in RESPONSE_TARGET_TEMPLATE:
        target = RESPONSE_TARGET_TEMPLATE.format(player=player)
    else:
        target = RESPONSE_TARGET_TEMPLATE

    try:
        rcon_client.send_tellraw(target, final_message)
    except Exception as e:
        logger.error(f"Error al enviar tellraw: {e}")

def process_ofrenda_request(player: str, item: str) -> None:
    """Procesa un sacrificio/ofrenda de un ítem por parte del jugador."""
    base_prob = get_item_probability(item)
    if base_prob <= 0.02:
        puntos_ganados = 100
        rarity_text = "ofrenda legendaria"
    elif base_prob <= 0.15:
        puntos_ganados = 40
        rarity_text = "ofrenda valiosa"
    elif base_prob <= 0.50:
        puntos_ganados = 15
        rarity_text = "ofrenda digna"
    else:
        puntos_ganados = 5
        rarity_text = "ofrenda modesta"
        
    try:
        rcon_response = rcon_client.execute_command(f"clear \"{player}\" {item} 1")
        rcon_lower = rcon_response.lower()
        if any(x in rcon_lower for x in ["no items", "could not", "error", "syntax", "unknown", "failed"]):
            logger.info(f"Ofrenda fallida para '{player}': no posee '{item}' o ítem inválido. RCON: {rcon_response}")
            rcon_client.send_tellraw(
                player,
                f"§6[§5Oráculo§6] §cNo posees '{item}' en tu inventario para ofrecerlo en sacrificio."
            )
            return
            
        # Ofrenda exitosa!
        try:
            rcon_client.execute_command(f"execute at \"{player}\" run playsound random.orb @s")
            rcon_client.execute_command(f"execute at \"{player}\" run particle minecraft:totem_particle ~ ~1 ~")
        except Exception:
            pass
            
        nueva_data = update_player_devocion(player, puntos_ganados)
        logger.info(f"Ofrenda exitosa de '{player}' ({item}). Devoción +{puntos_ganados}. Total: {nueva_data['puntos']}")
        
        response = ai_handler.generate_item_response(
            player_name=player,
            item=item,
            outcome="success",
            devocion_rango=nueva_data["rango"]
        )
        final_message = f"§6[§5Oráculo§6] §a{response} §e(+{puntos_ganados} Devoción, Rango: {nueva_data['rango']})"
        rcon_client.send_tellraw("@a", final_message)
        
    except Exception as e:
        logger.error(f"Error al procesar ofrenda: {e}")
        try:
            rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cLas flames del altar de ofrendas se han apagado repentinamente.")
        except Exception:
            pass

def process_clima_request(player: str, clima_tipo: str) -> None:
    """Cambia el clima si el jugador tiene suficiente devoción."""
    data = get_player_devocion_data(player)
    if data["puntos"] < 150 and player not in DIVINE_FAVOR_PLAYERS:
        try:
            rcon_client.send_tellraw(
                player,
                f"§6[§5Oráculo§6] §cTu devoción ({data['puntos']}/150) es insuficiente para alterar el clima."
            )
        except Exception:
            pass
        return

    clima_map = {
        "sol": "clear", "clear": "clear", "despejado": "clear",
        "lluvia": "rain", "rain": "rain",
        "tormenta": "thunder", "thunder": "thunder", "tempestad": "thunder"
    }
    
    cmd_weather = clima_map.get(clima_tipo.lower())
    if not cmd_weather:
        try:
            rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cClimas permitidos: sol, lluvia, tormenta.")
        except Exception:
            pass
        return
        
    try:
        rcon_client.execute_command(f"weather {cmd_weather}")
        try:
            rcon_client.execute_command(f"execute at \"{player}\" run playsound ambient.weather.thunder @a")
            rcon_client.execute_command(f"execute at \"{player}\" run particle minecraft:conduit_particle ~ ~2 ~")
        except Exception:
            pass
            
        costo = -25
        nueva_data = update_player_devocion(player, costo)
        
        response = ai_handler.generate_item_response(
            player_name=player,
            item=f"el clima a {clima_tipo}",
            outcome="success",
            devocion_rango=nueva_data["rango"]
        )
        final_msg = f"§6[§5Oráculo§6] §b{response} §e({costo} Devoción, Rango: {nueva_data['rango']})"
        rcon_client.send_tellraw("@a", final_msg)
    except Exception as e:
        logger.error(f"Error al cambiar clima: {e}")

def process_tiempo_request(player: str, tiempo_tipo: str) -> None:
    """Cambia la hora del día si el jugador tiene suficiente devoción."""
    data = get_player_devocion_data(player)
    if data["puntos"] < 150 and player not in DIVINE_FAVOR_PLAYERS:
        try:
            rcon_client.send_tellraw(
                player,
                f"§6[§5Oráculo§6] §cTu devoción ({data['puntos']}/150) es insuficiente para alterar el tiempo celestial."
            )
        except Exception:
            pass
        return

    tiempo_map = {
        "dia": "day", "day": "day", "sol": "day",
        "noche": "night", "night": "night", "oscuridad": "night"
    }
    
    cmd_time = tiempo_map.get(tiempo_tipo.lower())
    if not cmd_time:
        try:
            rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cTiempos permitidos: dia, noche.")
        except Exception:
            pass
        return
        
    try:
        rcon_client.execute_command(f"time set {cmd_time}")
        try:
            rcon_client.execute_command(f"execute at \"{player}\" run playsound mob.elder_guardian.curse @a")
            rcon_client.execute_command(f"execute at \"{player}\" run particle minecraft:spore_blossom_shower_particle ~ ~2 ~")
        except Exception:
            pass
            
        costo = -25
        nueva_data = update_player_devocion(player, costo)
        
        response = ai_handler.generate_item_response(
            player_name=player,
            item=f"el flujo del tiempo celestial hacia la {tiempo_tipo}",
            outcome="success",
            devocion_rango=nueva_data["rango"]
        )
        final_msg = f"§6[§5Oráculo§6] §b{response} §e({costo} Devoción, Rango: {nueva_data['rango']})"
        rcon_client.send_tellraw("@a", final_msg)
    except Exception as e:
        logger.error(f"Error al cambiar tiempo: {e}")

def process_riddle_request(player: str) -> None:
    """Genera un acertijo místico para el servidor."""
    global active_riddle, active_riddle_time
    
    remaining = check_cooldown(player)
    if remaining is not None:
        try:
            rcon_client.send_tellraw(
                player,
                f"§6[§5Oráculo§6] §cLos dioses no tienen tareas para ti aún. Espera {remaining} segundos."
            )
        except Exception:
            pass
        return
    
    last_query_times[player] = time.time()
    
    current_time = time.time()
    if active_riddle and (current_time - active_riddle_time < 300):
        try:
            rcon_client.send_tellraw(
                player,
                f"§6[§5Oráculo§6] §dYa hay un enigma activo: §e{active_riddle['riddle']}"
            )
        except Exception:
            pass
        return
        
    try:
        rcon_client.send_tellraw("@a", "§6[§5Oráculo§6] §dConsultando a las estrellas por un nuevo enigma...")
    except Exception:
        pass
        
    riddle_data = ai_handler.generate_riddle()
    active_riddle = riddle_data
    active_riddle_time = current_time
    
    msg = f"§6[§5Oráculo§6] §e§lENIGMA DIVINO: §d{riddle_data['riddle']} §7(Usa '!oraculo responder <palabra>')"
    try:
        rcon_client.send_tellraw("@a", msg)
        rcon_client.execute_command("execute at @a run playsound block.bell.use @s")
    except Exception as e:
        logger.error(f"Error al anunciar acertijo: {e}")

def process_answer_request(player: str, answer: str) -> None:
    """Verifica la respuesta dada por un jugador a un acertijo activo."""
    global active_riddle, active_riddle_time
    
    current_time = time.time()
    if not active_riddle or (current_time - active_riddle_time >= 300):
        try:
            rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cNo hay ningún enigma divino activo en este momento.")
        except Exception:
            pass
        return
        
    expected = active_riddle["answer"].lower().strip()
    if answer == expected:
        active_riddle = None
        nueva_data = update_player_devocion(player, 50)
        
        recompensas = ["gold_ingot", "emerald", "diamond", "iron_ingot"]
        item_recompensa = random.choice(recompensas)
        cant = 3 if item_recompensa in ["gold_ingot", "iron_ingot"] else 1
        
        try:
            rcon_client.execute_command(f"give \"{player}\" {item_recompensa} {cant}")
            rcon_client.execute_command(f"execute at \"{player}\" run playsound random.levelup @a")
            rcon_client.execute_command(f"execute at \"{player}\" run particle minecraft:villager_happy ~ ~1 ~")
            
            response = ai_handler.generate_item_response(
                player_name=player,
                item=f"la respuesta correcta del enigma y obtenido {cant} {item_recompensa}",
                outcome="success",
                devocion_rango=nueva_data["rango"]
            )
            final_msg = f"§6[§5Oráculo§6] §a{response} §e(+50 Devoción, Rango: {nueva_data['rango']})"
            rcon_client.send_tellraw("@a", final_msg)
        except Exception as e:
            logger.error(f"Error al otorgar recompensa de acertijo: {e}")
    else:
        nueva_data = update_player_devocion(player, -2)
        increase_wrath(1)
        logger.info(f"Respuesta incorrecta de '{player}' para el acertijo. Devoción -2. Total: {nueva_data['puntos']}")
        try:
            rcon_client.execute_command(f"execute at \"{player}\" run playsound random.glass @s")
            rcon_client.send_tellraw(
                player,
                f"§6[§5Oráculo§6] §cTu respuesta '{answer}' es incorrecta. La divinidad se aleja... (-2 Devoción, Rango: {nueva_data['rango']})"
            )
        except Exception:
            pass

def process_chat_message(player: str, message: str) -> None:
    """
    Procesa un mensaje de chat recibido del webhook del Behavior Pack.
    Reemplaza al antiguo log_callback para la entrada de datos del chat.

    Args:
        player: Nombre del jugador que envió el mensaje.
        message: Mensaje completo del chat (incluyendo el prefijo !oraculo).
    """
    # Verificar que el mensaje comienza con la palabra clave
    keyword_lower = COMMAND_KEYWORD.lower()
    msg_lower = message.lower().strip()

    if not msg_lower.startswith(keyword_lower):
        logger.debug(f"Mensaje ignorado (sin prefijo '{COMMAND_KEYWORD}'): {message}")
        return

    player_clean = player.strip()
    query_clean = message.strip()[len(COMMAND_KEYWORD):].strip()

    logger.info(f"Comando del Oráculo detectado de '{player_clean}': '{query_clean}'")

    # Detección de Insultos en la consulta del oráculo
    if check_for_insults(query_clean):
        execute_smite(player_clean, "insult_smited", query_clean)
        return

    tokens = query_clean.split()
    if not tokens:
        try:
            rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §d¿Qué buscas de mí, mortal? Habla y te responderé.")
        except Exception:
            pass
        return

    action = tokens[0].lower()

    if action == "quisiera":
        if len(tokens) < 2:
            try:
                rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cDebes especificar qué deseas pedir.")
            except Exception:
                pass
            return
        item = tokens[1]
        process_item_request(player_clean, item)

    elif action == "ofrenda":
        if len(tokens) < 2:
            try:
                rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cDebes especificar qué deseas ofrendar.")
            except Exception:
                pass
            return
        item = tokens[1]
        process_ofrenda_request(player_clean, item)

    elif action in ("clima", "weather"):
        if len(tokens) < 2:
            try:
                rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cEspecifica el clima: sol, lluvia o tormenta.")
            except Exception:
                pass
            return
        clima_tipo = tokens[1]
        process_clima_request(player_clean, clima_tipo)

    elif action in ("tiempo", "time"):
        if len(tokens) < 2:
            try:
                rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cEspecifica el tiempo: dia o noche.")
            except Exception:
                pass
            return
        tiempo_tipo = tokens[1]
        process_tiempo_request(player_clean, tiempo_tipo)

    elif action in ("mision", "riddle", "acertijo"):
        process_riddle_request(player_clean)

    elif action in ("responder", "respuesta", "solve"):
        if len(tokens) < 2:
            try:
                rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cEspecifica tu respuesta.")
            except Exception:
                pass
            return
        answer = tokens[1]
        process_answer_request(player_clean, answer)

    else:
        # Por defecto, localizar una estructura
        process_command(player_clean, action)


def process_server_event(event_type: str, player: str) -> None:
    """
    Procesa eventos de conexión/desconexión recibidos del Behavior Pack.

    Args:
        event_type: Tipo de evento ("player_join" o "player_leave").
        player: Nombre del jugador involucrado.
    """
    player_clean = player.strip()
    if event_type == "player_join":
        logger.info(f"[Evento BP] Jugador '{player_clean}' se ha conectado al servidor.")
        # Inicializar datos de devoción para jugadores nuevos
        get_player_devocion_data(player_clean)
    elif event_type == "player_leave":
        logger.info(f"[Evento BP] Jugador '{player_clean}' se ha desconectado del servidor.")


def main() -> None:
    """Función de entrada principal. Inicia el servidor webhook que recibe datos del Behavior Pack."""
    logger.info("==============================================")
    logger.info("Iniciando Bot Oráculo para Minecraft Bedrock")
    logger.info(f"Modo Revelar Coordenadas Exactas: {REVEAL_EXACT_COORDS}")
    logger.info(f"Cooldown general: {COOLDOWN_SECONDS}s")
    logger.info(f"Jugadores con Favor Divino: {DIVINE_FAVOR_PLAYERS}")
    logger.info(f"Webhook escuchando en puerto: {WEBHOOK_PORT}")
    logger.info("==============================================")

    webhook = WebhookServer(
        port=WEBHOOK_PORT,
        chat_callback=process_chat_message,
        event_callback=process_server_event,
        secret=WEBHOOK_SECRET if WEBHOOK_SECRET else None,
    )

    try:
        webhook.start()
    except KeyboardInterrupt:
        logger.info("Deteniendo el oráculo por KeyboardInterrupt...")
    finally:
        rcon_client.disconnect()
        logger.info("Bot Oráculo apagado completamente.")


if __name__ == "__main__":
    main()
