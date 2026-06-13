import os
import re
import sys
import math
import time
import random
import json
import logging
import queue
import threading
import difflib
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
# Configuración de la consola del BDS (reemplaza RCON, que no es soportado por Bedrock)
SCREEN_SESSION_NAME = os.getenv("SCREEN_SESSION_NAME", "minecraft")
SERVER_LOG_FILE = os.getenv("SERVER_LOG_FILE", "")
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

WORLD_SEED_STR = os.getenv("WORLD_SEED", "0")
try:
    WORLD_SEED = int(WORLD_SEED_STR)
except ValueError:
    WORLD_SEED = 0

# Lista de jugadores con Favor Divino
DIVINE_FAVOR_PLAYERS_RAW = os.getenv("DIVINE_FAVOR_PLAYERS", "")
DIVINE_FAVOR_PLAYERS: List[str] = [
    p.strip() for p in DIVINE_FAVOR_PLAYERS_RAW.split(",") if p.strip()
]

# Lista de administradores
ADMIN_PLAYERS_RAW = os.getenv("ADMIN_PLAYERS", "")
ADMIN_PLAYERS: List[str] = [
    p.strip() for p in ADMIN_PLAYERS_RAW.split(",") if p.strip()
]

# Asegurar que los admins no estén en favor divino (para evitar conflictos de lógica)
DIVINE_FAVOR_PLAYERS = [p for p in DIVINE_FAVOR_PLAYERS if p not in ADMIN_PLAYERS]


# Validaciones iniciales
if not OPENAI_API_KEY:
    logger.critical("Falta la variable OPENAI_API_KEY en el archivo .env. Saliendo...")
    sys.exit(1)
if not SERVER_LOG_FILE:
    logger.critical("Falta la variable SERVER_LOG_FILE en el archivo .env. Saliendo...")
    sys.exit(1)
if not LOG_FILE_PATH:
    logger.warning("LOG_FILE_PATH no configurado. El monitor de logs estará desactivado (solo se usará el webhook).")

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
cooldown_spam_count: Dict[str, int] = {}

# Estado del acertijo activo
active_riddle: Optional[dict] = None
active_riddle_time: float = 0.0
active_riddle_timer: Optional[threading.Timer] = None

# Lista de mobs seguros para castigos
SAFE_PUNISHMENT_MOBS = [
    "zombie", "skeleton", "creeper", "cave_spider", 
    "witch", "phantom", "silverfish", "slime"
]

# Ira divina global
global_wrath: int = 0

# Inicializar servicios
logger.info("Inicializando clientes y servicios...")
rcon_client = RCONClient(
    screen_name=SCREEN_SESSION_NAME,
    log_file=SERVER_LOG_FILE,
)
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

DEVOTION_RANKS = [
    (1000, "Predilecto"),
    (500, "Devoto"),
    (200, "Creyente"),
    (50, "Dudoso"),
    (0, "Hereje")
]

def get_player_devocion_data(player: str) -> dict:
    db = load_devocion()
    if player not in db:
        puntos = 50
        rango = "Dudoso"
        if player in ADMIN_PLAYERS:
            puntos = 9999
            rango = "Predilecto"
        elif player in DIVINE_FAVOR_PLAYERS:
            puntos = 500
            rango = "Devoto"
        db[player] = {
            "puntos": puntos,
            "rango": rango,
            "ultima_ofrenda": 0.0
        }
        save_devocion(db)
    else:
        # Forzar valores de admin si no estaban actualizados
        if player in ADMIN_PLAYERS and db[player].get("puntos", 0) != 9999:
            db[player]["puntos"] = 9999
            db[player]["rango"] = "Predilecto"
            save_devocion(db)
            
    return db[player]

def update_player_devocion(player: str, delta: int) -> dict:
    db = load_devocion()
    if player not in db:
        puntos = 50
        rango = "Dudoso"
        if player in ADMIN_PLAYERS:
            puntos = 9999
            rango = "Predilecto"
        elif player in DIVINE_FAVOR_PLAYERS:
            puntos = 500
            rango = "Devoto"
        db[player] = {
            "puntos": puntos,
            "rango": rango,
            "ultima_ofrenda": 0.0
        }
    
    data = db[player]
    
    if player in ADMIN_PLAYERS:
        data["puntos"] = 9999
        data["rango"] = "Predilecto"
    else:
        nuevos_puntos = data["puntos"] + delta
        if player in DIVINE_FAVOR_PLAYERS:
            nuevos_puntos = max(300, nuevos_puntos)  # Suelo VIP de 300 puntos
        else:
            nuevos_puntos = max(0, nuevos_puntos)
            
        data["puntos"] = nuevos_puntos
        
        for threshold, rank_name in DEVOTION_RANKS:
            if nuevos_puntos >= threshold:
                data["rango"] = rank_name
                break
        
    db[player] = data
    save_devocion(db)
    return data

# Estado de la Ira Global Activa
is_wrath_active: bool = False
wrath_canceled_by_player: Optional[str] = None
wrath_timer_thread: Optional[threading.Thread] = None

# ---- SISTEMA DE IRA DIVINA GLOBAL ----
def increase_wrath(amount: int) -> None:
    global global_wrath, is_wrath_active
    if is_wrath_active:
        return
    global_wrath += amount
    logger.info(f"Ira colectiva global incrementada en {amount}. Total actual: {global_wrath}/100")
    if global_wrath >= 100:
        global_wrath = 0
        trigger_wrath_event()

def trigger_wrath_event() -> None:
    global is_wrath_active, wrath_canceled_by_player, wrath_timer_thread
    if is_wrath_active:
        return
        
    is_wrath_active = True
    wrath_canceled_by_player = None
    logger.warning("¡Desatando la IRA DIVINA global en el servidor!")
    
    wrath_timer_thread = threading.Thread(target=wrath_active_loop)
    wrath_timer_thread.start()

def wrath_active_loop() -> None:
    global is_wrath_active, wrath_canceled_by_player
    
    try:
        rcon_client.execute_command("time set midnight")
        rcon_client.execute_command("weather thunder")
        rcon_client.execute_command("title @a title §4LA IRA DE LOS DIOSES")
        rcon_client.execute_command("execute at @a run playsound mob.enderdragon.growl @s")
        rcon_client.execute_command("effect @a blindness 60 1 true")
        rcon_client.execute_command("effect @a nausea 60 1 true")
        rcon_client.execute_command("effect @a mining_fatigue 60 2 true")
    except Exception as e:
        logger.error(f"Error al iniciar atmósfera de ira: {e}")

    # Silencio tenso de 7 segundos
    for _ in range(7):
        if not is_wrath_active:
            break
        time.sleep(1)
        
    if not is_wrath_active:
        end_wrath_event()
        return

    try:
        resp = rcon_client.execute_command("list")
        players_online = []
        if "players online:" in resp.lower():
            lines = resp.split("\n")
            if len(lines) > 1:
                players_raw = lines[1].split(",")
                players_online = [p.strip() for p in players_raw if p.strip()]
        
        for p in players_online:
            if p not in DIVINE_FAVOR_PLAYERS:
                if random.random() <= 0.40:
                    rcon_client.execute_command(f"execute at \"{p}\" run summon creeper ~2 ~ ~2")
                    logger.info(f"Creeper de ira spawneado cerca de '{p}'")
    except Exception as e:
        logger.error(f"Error al spawnear creepers en ira: {e}")

    # Bucle de rayos durante ~54 segundos (27 iteraciones de 2s)
    iterations = 27
    for _ in range(iterations):
        if not is_wrath_active:
            break
        try:
            offset_x = random.choice([-4, -3, 3, 4])
            offset_z = random.choice([-4, -3, 3, 4])
            rcon_client.execute_command(f"execute at @a run summon lightning_bolt ~{offset_x} ~ ~{offset_z}")
        except Exception:
            pass
        time.sleep(2)
        
    if is_wrath_active:
        end_wrath_event()

def end_wrath_event() -> None:
    global is_wrath_active, wrath_canceled_by_player
    is_wrath_active = False
    
    try:
        rcon_client.execute_command("weather clear")
        rcon_client.execute_command("time set day")
        rcon_client.execute_command("effect @a clear")
    except Exception:
        pass
        
    final_response = ai_handler.generate_wrath_end_response(canceled_by=wrath_canceled_by_player)
    final_message = f"§6[§5Oráculo§6] §d{final_response}"
    try:
        rcon_client.send_tellraw("@a", final_message)
    except Exception:
        pass

def get_online_players() -> List[str]:
    """Obtiene la lista de jugadores conectados actualmente usando el comando list."""
    try:
        resp = rcon_client.execute_command("list")
        if "players online:" in resp.lower():
            lines = resp.split("\n")
            if len(lines) > 1:
                players_raw = lines[1].split(",")
                return [p.strip() for p in players_raw if p.strip()]
    except Exception as e:
        logger.error(f"Error al obtener jugadores online: {e}")
    return []

def fuzzy_match_player(target_name: str) -> Optional[str]:
    """
    Busca al jugador más similar en la lista de conectados.
    Requiere al menos 80% de similitud para considerarse válido.
    """
    online_players = get_online_players()
    if not online_players:
        return None
        
    matches = difflib.get_close_matches(target_name, online_players, n=1, cutoff=0.8)
    if matches:
        return matches[0]
    return None

# Expresiones regulares
# Detección del chat del jugador y extracción de la consulta completa
CHAT_EXTRACT_PATTERN = re.compile(
    rf"(?:<(?P<player1>[^>]+)>\s*|(?P<player2>[a-zA-Z0-9_ ]+):\s*){re.escape(COMMAND_KEYWORD)}(?:\s+(?P<query>.*))?"
)

# Coordenadas numéricas generales (locate de estructura)
COORDS_PATTERN = re.compile(r"block\s+(-?\d+)\s*,\s*(?:\(y\?\)|-?\d+|~)\s*,\s*(-?\d+)\s*\(\s*(\d+)\s*blocks\s+away\s*\)", re.IGNORECASE)

# Coordenadas del jugador (teleport)
PLAYER_COORDS_PATTERN = re.compile(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)")

# Mapeo COMPLETO de nombres de biomas Java/comunes → Bedrock Resource Location
# Fuente: https://minecraft.wiki/w/Biome/ID (tabla Bedrock Edition)
# Solo incluye entradas donde el ID de Bedrock difiere del nombre común/Java.
# El comando de Bedrock es: /locate biome minecraft:<bedrock_id>
BEDROCK_BIOME_MAPPING = {
    # Pantanos
    "swamp": "swampland",
    "swamp_hills": "swampland_mutated",
    # Badlands / Mesa
    "badlands": "mesa",
    "eroded_badlands": "mesa_bryce",
    "wooded_badlands": "mesa_plateau_stone",
    "wooded_badlands_plateau": "mesa_plateau_stone",
    "badlands_plateau": "mesa_plateau",
    "modified_badlands_plateau": "mesa_plateau_mutated",
    "modified_wooded_badlands_plateau": "mesa_plateau_stone_mutated",
    # Bosques oscuros
    "dark_forest": "roofed_forest",
    "dark_forest_hills": "roofed_forest_mutated",
    # Champiñones
    "mushroom_fields": "mushroom_island",
    "mushroom_field_shore": "mushroom_island_shore",
    # Taigas
    "snowy_taiga": "cold_taiga",
    "snowy_taiga_hills": "cold_taiga_hills",
    "snowy_taiga_mountains": "cold_taiga_mutated",
    "old_growth_pine_taiga": "mega_taiga",
    "old_growth_spruce_taiga": "redwood_taiga_mutated",
    "giant_tree_taiga_hills": "mega_taiga_hills",
    "giant_spruce_taiga_hills": "redwood_taiga_hills_mutated",
    "taiga_mountains": "taiga_mutated",
    # Llanuras nevadas
    "snowy_tundra": "ice_plains",
    "snowy_plains": "ice_plains",
    "snowy_mountains": "ice_mountains",
    "ice_spikes": "ice_plains_spikes",
    # Colinas ventosas / Montañas extremas
    "windswept_hills": "extreme_hills",
    "windswept_forest": "extreme_hills_plus_trees",
    "windswept_gravelly_hills": "extreme_hills_mutated",
    "windswept_savanna": "savanna_mutated",
    # Selvas
    "sparse_jungle": "jungle_edge",
    "modified_jungle": "jungle_mutated",
    "modified_jungle_edge": "jungle_edge_mutated",
    # Sabanas
    "shattered_savanna_plateau": "savanna_plateau_mutated",
    # Playas
    "stony_shore": "stone_beach",
    "snowy_beach": "cold_beach",
    # Bosques de abedules
    "old_growth_birch_forest": "birch_forest_mutated",
    "tall_birch_hills": "birch_forest_hills_mutated",
    # Desiertos
    "desert_lakes": "desert_mutated",
    # Llanuras
    # "plains", "sunflower_plains" → idénticos en Bedrock
    # Nether
    # "nether_wastes", "soul_sand_valley", "crimson_forest", "warped_forest", "basalt_deltas" → idénticos
    # End
    # "the_end" → idénticos
    # Nuevos biomas 1.18+ (idénticos en Bedrock y Java)
    # "meadow", "grove", "snowy_slopes", "frozen_peaks", "jagged_peaks", "stony_peaks",
    # "cherry_grove", "dripstone_caves", "lush_caves", "deep_dark" → idénticos
    # Mangrove Swamp → "mangrove_swamp" idéntico en Bedrock
    # Pale Garden → "pale_garden" idéntico en Bedrock
}

# ─── Sistema de Validación de Tamaño de Biomas ──────────────────
# Máximo de intentos para encontrar un bioma grande
MAX_BIOME_SEARCH_ATTEMPTS = 3

# Distancia en bloques para desplazar el punto de búsqueda en cada retry
BIOME_RETRY_OFFSET = 500

# Cola thread-safe para recibir resultados de biome-check del Behavior Pack
biome_result_queue: queue.Queue = queue.Queue()

# Mensajes progresivos que el Oráculo envía al jugador entre intentos de búsqueda.
# Temática RP para disfrazar la latencia.
BIOME_SEARCH_MESSAGES = [
    "§6[§5Oráculo§6] §dLas estrellas están escrutando las tierras de {biome}...",
    "§6[§5Oráculo§6] §eEsa tierra era demasiado estrecha... El Oráculo extiende su mirada más allá del horizonte...",
    "§6[§5Oráculo§6] §eUn segundo fragmento fue hallado, pero era solo una sombra. Buscando tierras más vastas...",
]


def _add_tickingarea(x: float, z: float, name: str) -> None:
    """Crea una tickingarea circular temporal para cargar chunks alrededor de (x, z)."""
    try:
        cmd = f"tickingarea add circle {int(x)} 0 {int(z)} 4 {name}"
        rcon_client.execute_command(cmd)
        logger.info(f"Tickingarea '{name}' creada en ({int(x)}, {int(z)})")
    except Exception as e:
        logger.warning(f"Error creando tickingarea '{name}': {e}")


def _remove_tickingarea(name: str) -> None:
    """Elimina una tickingarea temporal por nombre."""
    try:
        rcon_client.execute_command(f"tickingarea remove {name}")
        logger.info(f"Tickingarea '{name}' eliminada")
    except Exception as e:
        logger.warning(f"Error eliminando tickingarea '{name}': {e}")


def _locate_biome_from_offset(
    origin_x: float, origin_z: float,
    biome_x: float, biome_z: float,
    bedrock_biome: str, offset_distance: float = 500.0
) -> Optional[str]:
    """
    Ejecuta /locate biome desde una posición offset usando un armor_stand temporal.
    
    Calcula el offset en la dirección opuesta al jugador (origin → biome → más allá),
    crea un tickingarea, summonea un armor_stand con tag, ejecuta locate desde él,
    y limpia todo al terminar.
    
    Returns:
        La respuesta cruda del comando locate, o None si falló.
    """
    # Calcular dirección normalizada (origin → biome → más allá)
    dx = biome_x - origin_x
    dz = biome_z - origin_z
    mag = math.sqrt(dx * dx + dz * dz) or 1.0
    offset_x = int(biome_x + (dx / mag) * offset_distance)
    offset_z = int(biome_z + (dz / mag) * offset_distance)

    logger.info(f"Retry: buscando desde offset ({offset_x}, {offset_z})")

    try:
        # 1. Crear tickingarea en la zona offset
        _add_tickingarea(offset_x, offset_z, "oraculo_retry")
        time.sleep(2.0)  # Esperar a que carguen los chunks

        # 2. Summonear armor_stand y asignar tag
        rcon_client.execute_command(
            f"summon armor_stand {offset_x} 300 {offset_z}"
        )
        time.sleep(0.5)
        rcon_client.execute_command(
            f"tag @e[type=armor_stand,x={offset_x},y=300,z={offset_z},r=5] add oraculo_probe"
        )
        time.sleep(0.3)

        # 3. Ejecutar locate desde el armor_stand
        rcon_response = rcon_client.execute_command(
            f'execute as @e[tag=oraculo_probe] at @s run locate biome minecraft:{bedrock_biome}',
            max_wait=5.0
        )
        logger.info(f"Retry locate response: '{rcon_response.strip()}'")

        return rcon_response

    except Exception as e:
        logger.error(f"Error en _locate_biome_from_offset: {e}")
        return None

    finally:
        # 4. Cleanup: matar entidad + remover tickingarea
        try:
            rcon_client.execute_command("kill @e[tag=oraculo_probe]")
        except Exception:
            pass
        _remove_tickingarea("oraculo_retry")


# Lista de palabras consideradas insultos al Oráculo
INSULTS = [
    "tonto", "tonta", "estupido", "estúpido", "estupida", "estúpida", "idiota", "puto", 
    "puta", "mierda", "basura", "pendejo", "culero", "culera", "maricon", "cabron", 
    "cabrón", "feo", "fea", "inutil", "inútil", "inservible", "estupidez", "imbecil", "imbécil"
]

# Sistema categorizado de probabilidades de ítems
ITEM_CATEGORIES = [
    ("divine", 0.005, ["netherite", "elytra", "totem", "beacon", "shulker", "star", "dragon", "enchanted_golden_apple"]),
    ("rare", 0.05, ["diamond", "emerald", "gold", "pearl", "tnt", "obsidian", "crystal", "sword", "golden_apple"]),
    ("uncommon", 0.25, ["iron", "chainmail", "redstone", "lapis", "copper", "shears", "shield", "bow", "arrow"]),
    ("potion", 0.15, ["potion"]),
    ("common", 0.60, [])  # Fallback
]

# Mapeo de ítems con Data Values (para pociones en Bedrock)
BEDROCK_ITEM_MAPPING = {
    "axe": ("iron_axe", 0),
    "sword": ("iron_sword", 0),
    "pickaxe": ("iron_pickaxe", 0),
    "shovel": ("iron_shovel", 0),
    "hoe": ("iron_hoe", 0),
    "helmet": ("iron_helmet", 0),
    "chestplate": ("iron_chestplate", 0),
    "leggings": ("iron_leggings", 0),
    "boots": ("iron_boots", 0),
    "potion_of_night_vision": ("potion", 5),
    "potion_of_invisibility": ("potion", 7),
    "potion_of_leaping": ("potion", 9),
    "potion_of_fire_resistance": ("potion", 12),
    "potion_of_swiftness": ("potion", 14),
    "potion_of_slowness": ("potion", 17),
    "potion_of_water_breathing": ("potion", 19),
    "potion_of_healing": ("potion", 21),
    "potion_of_harming": ("potion", 23),
    "potion_of_poison": ("potion", 25),
    "potion_of_regeneration": ("potion", 28),
    "potion_of_strength": ("potion", 31),
    "potion_of_weakness": ("potion", 34),
    "potion_of_decay": ("potion", 36),
    "potion_of_turtle_master": ("potion", 37),
    "potion_of_slow_falling": ("potion", 40),
    "splash_potion_of_regeneration": ("splash_potion", 28),
    "splash_potion_of_healing": ("splash_potion", 21),
    "splash_potion_of_poison": ("splash_potion", 25),
    "splash_potion_of_weakness": ("splash_potion", 34)
}

def get_item_probability(item: str) -> float:
    """Retorna la probabilidad base de obtener un ítem usando clasificación ordenada por categorías."""
    item = item.lower()
    for cat_name, base_prob, keywords in ITEM_CATEGORIES:
        if any(k in item for k in keywords):
            return base_prob
    # Fallback si no coincide con nada, retorna "common"
    return ITEM_CATEGORIES[-1][1]

def check_for_insults(text: str) -> bool:
    """Verifica si la consulta contiene algún insulto en la lista."""
    text_lower = text.lower()
    for insult in INSULTS:
        pattern = rf"\b{re.escape(insult)}\b"
        if re.search(pattern, text_lower):
            return True
    return False

def calculate_relative_position(player_x: float, player_z: float, target_x: float, target_z: float) -> dict:
    """Calcula la distancia y dirección cardinal de jugador a estructura."""
    distance = int(round(math.dist((player_x, player_z), (target_x, target_z))))
    
    # En Minecraft Z es positivo hacia el sur y negativo hacia el norte
    # X es positivo hacia el este y negativo hacia el oeste
    dx = target_x - player_x
    dz = target_z - player_z

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

    return {"distance": distance, "direction": direction}

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

def handle_cooldown(player: str) -> bool:
    """Verifica el cooldown y maneja el castigo por spam (Regla de Tres). Retorna True si debe abortar."""
    remaining = check_cooldown(player)
    if remaining is not None:
        cooldown_spam_count[player] = cooldown_spam_count.get(player, 0) + 1
        spam = cooldown_spam_count[player]
        logger.info(f"Jugador '{player}' en cooldown. Spam count: {spam}/3. Restante: {remaining}s")
        
        if spam == 1:
            try:
                rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cLas estrellas aún se están alineando. Ten paciencia, mortal.")
            except Exception:
                pass
        elif spam == 2:
            try:
                rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §e¿Acaso eres sordo? He dicho que ESPERES. No tientes a tu suerte.")
                rcon_client.execute_command(f"execute at \"{player}\" run summon lightning_bolt ~3 ~ ~3")
            except Exception:
                pass
        elif spam >= 3:
            cooldown_spam_count[player] = 0
            execute_smite(player, "impatience_smited", "tiempo")
            
        return True
        
    # Cooldown expirado, resetear contador de spam
    cooldown_spam_count[player] = 0
    return False

def execute_smite(player: str, reason_outcome: str, target_item: str = "", amount: int = 1) -> None:
    """Fulmina al jugador con un rayo divino (smite) y lo elimina del juego."""
    logger.warning(f"¡SMITE disparado para el jugador '{player}' debido a: {reason_outcome}!")
    
    # Restar devoción e incrementar ira colectiva
    if reason_outcome == "insult_smited":
        nueva_data = update_player_devocion(player, -150)
        increase_wrath(25)
    elif reason_outcome == "impatience_smited":
        nueva_data = update_player_devocion(player, -50)
        increase_wrath(10)
    else:
        nueva_data = update_player_devocion(player, -100)
        increase_wrath(20)

    # 1. Ejecutar RCON para invocar rayo y matar al jugador
    try:
        rcon_client.execute_command(f"execute at \"{player}\" run playsound mob.elder_guardian.curse @a")
        rcon_client.execute_command(f"execute at \"{player}\" run summon lightning_bolt")
        rcon_client.execute_command(f"kill \"{player}\"")
        
        # Castigo destructivo: Rayos extra para quemar loot si es Favor Divino y un insulto
        if reason_outcome == "insult_smited" and player in DIVINE_FAVOR_PLAYERS:
            rcon_client.execute_command(f"execute at \"{player}\" run summon lightning_bolt ~ ~ ~")
            rcon_client.execute_command(f"execute at \"{player}\" run summon lightning_bolt ~ ~ ~")
            logger.info(f"Rayos adicionales ejecutados para quemar loot de '{player}'.")
            
    except Exception as e:
        logger.error(f"Error al ejecutar comandos RCON de smite: {e}")

    # 2. Obtener respuesta poética del LLM
    mystical_message = ai_handler.generate_item_response(
        player_name=player,
        item=target_item,
        outcome=reason_outcome,
        devocion_rango=nueva_data["rango"],
        amount=amount
    )
    final_message = f"§6[§5Oráculo§6] §c{mystical_message}"

    # 3. Anunciar globalmente a todos los jugadores
    try:
        rcon_client.send_tellraw("@a", final_message)
    except Exception as e:
        logger.error(f"Error al enviar mensaje global de smite: {e}")

def process_item_request(player: str, item: str, amount: int = 1) -> None:
    """Maneja la lógica de petición de ítems con probabilidades, cooldown, codicia, castigos y devoción."""
    # 1. Verificar Cooldown
    if handle_cooldown(player):
        return

    # Registrar tiempo de la consulta
    last_query_times[player] = time.time()
    
    # Obtener devoción del jugador
    devocion_data = get_player_devocion_data(player)
    puntos = devocion_data["puntos"]

    # 2. Calcular probabilidades basadas en devoción (de 1x a 5x multiplicador)
    base_prob = get_item_probability(item)
    mult = 1.0 + 4.0 * min(1.0, puntos / 500.0)
    
    if amount <= 10:
        divisor = math.sqrt(amount)
    else:
        divisor = math.sqrt(10) + (amount - 10) * 0.5
        
    final_prob = min(1.0, base_prob * mult) / divisor

    roll = random.random()
    logger.info(f"Petición de ítem '{item}' x{amount} por '{player}'. Probabilidad: {final_prob:.2%}, Dado tirado: {roll:.2%}")

    # 3. Resolución: Éxito
    if roll <= final_prob:
        failed_requests_count[player] = 0  # Resetear codicia
        
        # 15% de Capricho Divino (falso rechazo)
        if random.random() <= 0.15:
            logger.info(f"Rechazo por capricho divino a '{player}'.")
            try:
                rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §dLos astros han escuchado tu plegaria, pero han decidido ignorarla por capricho. Inténtalo de nuevo más tarde.")
            except Exception:
                pass
            return
            
        logger.info(f"¡Éxito! Concediendo '{item}' a '{player}'")
        
        # Dar ítem
        try:
            give_cmd = f"give \"{player}\" {item} {amount}"
            if item.lower() in BEDROCK_ITEM_MAPPING:
                mapped_item, mapped_data = BEDROCK_ITEM_MAPPING[item.lower()]
                give_cmd = f"give \"{player}\" {mapped_item} {amount} {mapped_data}"
                
            rcon_client.execute_command(give_cmd)
            rcon_client.execute_command(f"execute at \"{player}\" run playsound random.levelup @a")
            rcon_client.execute_command(f"execute at \"{player}\" run particle minecraft:totem_particle ~ ~1 ~")
        except Exception as e:
            logger.error(f"Error al dar el ítem vía RCON: {e}")

        # Otorgar devoción por buena fe
        nueva_data = update_player_devocion(player, 10)

        # Generar respuesta IA
        response = ai_handler.generate_item_response(
            player_name=player, item=item, outcome="success", devocion_rango=nueva_data["rango"], amount=amount
        )
        final_message = f"§6[§5Oráculo§6] §a{response}"
        
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
                if player in DIVINE_FAVOR_PLAYERS:
                    # Castigo menor para Favor Divino
                    logger.warning(f"Castigo menor para Favor Divino '{player}' en vez de smite.")
                    try:
                        rcon_client.execute_command(f"effect \"{player}\" blindness 20 1 true")
                        rcon_client.execute_command(f"effect \"{player}\" poison 10 0 true")
                        rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cTu codicia casi agota mi paciencia divina. Agradece tu suerte y sufre en silencio.")
                    except Exception as e:
                        logger.error(f"Error al aplicar castigo menor a Favor Divino: {e}")
                else:
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
                    player_name=player, item=item, outcome="punished", effect=effect_name, devocion_rango=nueva_data["rango"], amount=amount
                )
                final_message = f"§6[§5Oráculo§6] §c{response}"
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
                player_name=player, item=item, outcome="fail", devocion_rango=nueva_data["rango"], amount=amount
            )
            final_message = f"§6[§5Oráculo§6] §d{response}"
            try:
                rcon_client.send_tellraw("@a", final_message)
            except Exception:
                pass

def process_command(player: str, structure: str) -> None:
    """Orquesta la localización de estructuras."""
    if handle_cooldown(player):
        return

    last_query_times[player] = time.time()
    logger.info(f"Procesando solicitud de '{player}' para buscar '{structure}'")

    devocion_data = get_player_devocion_data(player)
    
    p_x, p_z = None, None
    s_x, s_z = None, None
    distance, direction = None, None

    # Teleport para posición de jugador
    try:
        cmd = f"execute as \"{player}\" at @s run teleport @s ~ ~ ~"
        tp_response = rcon_client.execute_command(cmd)
        logger.info(f"Respuesta cruda de teleport para '{player}': '{tp_response.strip()}'")
        match_p_coords = PLAYER_COORDS_PATTERN.search(tp_response)
        if match_p_coords:
            p_x = float(match_p_coords.group(1))
            p_z = float(match_p_coords.group(3))
            logger.info(f"Coordenadas del jugador '{player}': X={p_x}, Z={p_z}")
        else:
            logger.warning(f"No se pudo extraer coordenadas del jugador de la respuesta: '{tp_response.strip()}'")
    except Exception as e:
        logger.warning(f"No se pudo obtener la posición del jugador '{player}': {e}")

    # Locate estructura
    rcon_response = ""
    try:
        cmd = f"execute as \"{player}\" at @s run locate structure {structure}"
        # El locate puede tardar más que otros comandos; darle más tiempo
        rcon_response = rcon_client.execute_command(cmd, max_wait=5.0)
        
        logger.info(f"Respuesta cruda de locate: '{rcon_response.strip()}'")
        
    except Exception as e:
        logger.error(f"Error CRÍTICO de ejecución o conexión al buscar estructura: {e}", exc_info=True)
        try:
            rcon_client.send_tellraw(
                "@a",
                "§6[§5Oráculo§6] §cLos astros tiemblan y la conexión espiritual con el servidor se ha quebrado."
            )
        except Exception:
            pass
        return False

    # Extraer coordenadas de estructura
    match_coords = COORDS_PATTERN.search(rcon_response)
    if match_coords:
        s_x_str = match_coords.group(1)
        s_z_str = match_coords.group(2)
        dist_str = match_coords.group(3)
        logger.info(f"Coordenadas de estructura extraídas: X={s_x_str}, Z={s_z_str}, Dist={dist_str}")
        try:
            s_x = float(s_x_str)
            s_z = float(s_z_str)
            distance = float(dist_str)
        except ValueError:
            logger.warning(f"Error al convertir coordenadas de estructura a float: X='{s_x_str}', Z='{s_z_str}', Dist='{dist_str}'")
    else:
        logger.warning(
            f"COORDS_PATTERN no coincidió con la respuesta del locate. "
            f"Respuesta: '{rcon_response.strip()}'. "
            f"Patrón esperado: 'block X, (y?), Z (N blocks away)'"
        )

    # Calcular rumbo/distancia euclidiana exacta
    if p_x is not None and p_z is not None and s_x is not None and s_z is not None:
        rel_pos = calculate_relative_position(p_x, p_z, s_x, s_z)
        direction = rel_pos["direction"]
        # Usamos siempre la distancia euclidiana calculada (pasos exactos) en lugar del string de Bedrock
        distance = rel_pos["distance"]
        logger.info(f"Posición relativa calculada: {distance} pasos hacia {direction}")

    # Otorgar o restar devoción según si se encontró la estructura
    if match_coords:
        nueva_data = update_player_devocion(player, 2)
        try:
            rcon_client.execute_command(f"execute at \"{player}\" run playsound block.respawn_anchor.charge @s")
        except Exception:
            pass
    else:
        logger.warning(f"Estructura '{structure}' NO encontrada para '{player}'. Se restará devoción.")
        nueva_data = update_player_devocion(player, -2)
        increase_wrath(1)

    # Generar respuesta
    mystical_message = ai_handler.generate_response(
        player_name=player,
        structure=structure,
        distance=distance,
        direction=direction,
        devocion_rango=nueva_data["rango"]
    )

    final_message = f"§6[§5Oráculo§6] §d{mystical_message}"

    if "{player}" in RESPONSE_TARGET_TEMPLATE:
        target = RESPONSE_TARGET_TEMPLATE.format(player=player)
    else:
        target = RESPONSE_TARGET_TEMPLATE

    try:
        rcon_client.send_tellraw(target, final_message)
    except Exception as e:
        logger.error(f"Error al enviar tellraw: {e}")

def process_biome_request(player: str, target_biome: str) -> None:
    """Orquesta la localización de biomas con validación de tamaño.
    
    Flujo:
    1. Obtener posición del jugador
    2. /locate biome → P1
    3. Validar tamaño de P1 via scriptevent → Behavior Pack (getBiome sampling)
    4. Si es pequeño, buscar más lejos usando armor_stand temporal
    5. Repetir hasta encontrar uno grande o agotar intentos
    """
    if handle_cooldown(player):
        return

    last_query_times[player] = time.time()
    logger.info(f"Procesando solicitud de '{player}' para buscar bioma '{target_biome}'")

    devocion_data = get_player_devocion_data(player)
    
    p_x, p_z = None, None
    s_x, s_z = None, None
    distance, direction = None, None

    # ─── Paso 1: Obtener posición del jugador ───────────────────
    try:
        cmd = f"execute as \"{player}\" at @s run teleport @s ~ ~ ~"
        tp_response = rcon_client.execute_command(cmd)
        match_p_coords = PLAYER_COORDS_PATTERN.search(tp_response)
        if match_p_coords:
            p_x = float(match_p_coords.group(1))
            p_z = float(match_p_coords.group(3))
        else:
            logger.warning(f"No se pudo extraer coordenadas del jugador de la respuesta: '{tp_response.strip()}'")
    except Exception as e:
        logger.warning(f"No se pudo obtener la posición del jugador '{player}': {e}")
        return

    if p_x is None or p_z is None:
        logger.warning(f"Coordenadas del jugador no disponibles, abortando búsqueda de bioma")
        return

    bedrock_biome = BEDROCK_BIOME_MAPPING.get(target_biome.lower(), target_biome.lower())
    logger.info(f"Mapeo de bioma: '{target_biome}' -> '{bedrock_biome}' (Bedrock ID)")

    # ─── Paso 2: Bucle de búsqueda con validación de tamaño ────
    best_result = None  # (x, z, match_count) — mejor resultado encontrado
    last_found_x, last_found_z = None, None  # último bioma encontrado (para calcular offset)

    for attempt in range(MAX_BIOME_SEARCH_ATTEMPTS):
        # Enviar mensaje progresivo al jugador
        msg_idx = min(attempt, len(BIOME_SEARCH_MESSAGES) - 1)
        try:
            rcon_client.send_tellraw("@a", BIOME_SEARCH_MESSAGES[msg_idx].format(biome=target_biome))
        except Exception:
            pass

        # ── Locate biome ──
        rcon_response = ""
        if attempt == 0:
            # Primer intento: buscar desde la posición del jugador
            try:
                cmd = f'execute as "{player}" at @s run locate biome minecraft:{bedrock_biome}'
                logger.info(f"[Intento {attempt+1}] Comando: [{cmd}]")
                rcon_response = rcon_client.execute_command(cmd, max_wait=5.0)
                logger.info(f"[Intento {attempt+1}] Respuesta: '{rcon_response.strip()}'")
            except Exception as e:
                logger.error(f"[Intento {attempt+1}] Error al buscar bioma: {e}")
                break
        else:
            # Retry: buscar desde una posición offset usando armor_stand
            if last_found_x is not None and last_found_z is not None:
                rcon_response = _locate_biome_from_offset(
                    origin_x=p_x, origin_z=p_z,
                    biome_x=last_found_x, biome_z=last_found_z,
                    bedrock_biome=bedrock_biome,
                    offset_distance=BIOME_RETRY_OFFSET
                ) or ""
            else:
                logger.warning(f"[Intento {attempt+1}] No hay coordenadas previas para offset, abortando")
                break

        # ── Parsear coordenadas ──
        match_coords = COORDS_PATTERN.search(rcon_response)
        if not match_coords:
            logger.warning(f"[Intento {attempt+1}] No se encontró bioma '{target_biome}'. Respuesta: {rcon_response}")
            break

        found_x = float(match_coords.group(1))
        found_z = float(match_coords.group(2))
        last_found_x, last_found_z = found_x, found_z
        logger.info(f"[Intento {attempt+1}] Bioma encontrado en X={found_x}, Z={found_z}")

        # ── Validar tamaño via scriptevent → Behavior Pack ──
        request_id = f"{player}_{attempt}_{int(time.time())}"

        # Drenar la cola de resultados previos que pudieran haber quedado
        while not biome_result_queue.empty():
            try:
                biome_result_queue.get_nowait()
            except queue.Empty:
                break

        # Crear tickingarea temporal para cargar chunks
        _add_tickingarea(found_x, found_z, "oraculo_probe")
        time.sleep(1.5)  # Esperar carga de chunks

        # Enviar scriptevent al Behavior Pack para sampling
        try:
            se_payload = json.dumps({
                "x": int(found_x),
                "z": int(found_z),
                "biome": bedrock_biome,
                "requestId": request_id
            })
            rcon_client.execute_command(f'scriptevent oraculo:biome_check {se_payload}')
            logger.info(f"[Intento {attempt+1}] scriptevent enviado: {se_payload}")
        except Exception as e:
            logger.error(f"[Intento {attempt+1}] Error enviando scriptevent: {e}")
            _remove_tickingarea("oraculo_probe")
            # Asumir que es válido si no podemos validar
            best_result = (found_x, found_z, -1)
            break

        # Esperar resultado del BP via la cola (con timeout)
        try:
            result = biome_result_queue.get(timeout=10.0)
            _remove_tickingarea("oraculo_probe")

            match_count = result.get("matchCount", 0)
            is_large = result.get("isLarge", False)
            checked = result.get("checkedCount", 0)

            logger.info(
                f"[Intento {attempt+1}] Resultado BP: {match_count}/{checked} probes, "
                f"isLarge={is_large}"
            )

            # Guardar como mejor resultado si supera al anterior
            if best_result is None or match_count > best_result[2]:
                best_result = (found_x, found_z, match_count)

            if is_large:
                logger.info(f"[Intento {attempt+1}] ✓ Bioma grande encontrado en ({found_x}, {found_z})")
                break
            else:
                logger.info(
                    f"[Intento {attempt+1}] ✗ Bioma demasiado pequeño ({match_count}/{checked}), "
                    f"buscando más lejos..."
                )
                # Continuar al siguiente intento

        except queue.Empty:
            logger.warning(f"[Intento {attempt+1}] Timeout esperando resultado del BP (10s)")
            _remove_tickingarea("oraculo_probe")
            # Asumir como válido si no hay respuesta del BP
            if best_result is None:
                best_result = (found_x, found_z, 0)
            break

    # ─── Paso 3: Usar el mejor resultado encontrado ─────────────
    if best_result is not None:
        s_x, s_z = best_result[0], best_result[1]
        rel_pos = calculate_relative_position(p_x, p_z, s_x, s_z)
        direction = rel_pos["direction"]
        distance = rel_pos["distance"]
        logger.info(
            f"Resultado final: bioma '{target_biome}' en X={s_x}, Z={s_z}. "
            f"Distancia={distance}, Dirección={direction}, matchScore={best_result[2]}"
        )

    # ─── Paso 4: Otorgar o restar devoción ──────────────────────
    if s_x is not None and s_z is not None:
        nueva_data = update_player_devocion(player, 2)
        try:
            rcon_client.execute_command(f"execute at \"{player}\" run playsound block.respawn_anchor.charge @s")
        except Exception:
            pass
    else:
        nueva_data = update_player_devocion(player, -2)
        increase_wrath(1)

    # ─── Paso 5: Generar y enviar respuesta mística ─────────────
    mystical_message = ai_handler.generate_response(
        player_name=player,
        target_name=target_biome,
        distance=distance,
        direction=direction,
        devocion_rango=nueva_data["rango"],
        target_type="biome"
    )

    final_message = f"§6[§5Oráculo§6] §d{mystical_message}"

    if "{player}" in RESPONSE_TARGET_TEMPLATE:
        target = RESPONSE_TARGET_TEMPLATE.format(player=player)
    else:
        target = RESPONSE_TARGET_TEMPLATE

    try:
        rcon_client.send_tellraw(target, final_message)
    except Exception as e:
        logger.error(f"Error al enviar tellraw de bioma: {e}")

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
        rcon_response = rcon_client.execute_command(f"clear \"{player}\" {item} 0 1")
        rcon_lower = rcon_response.lower()
        if any(x in rcon_lower for x in ["no items", "could not", "error", "syntax", "unknown", "failed"]):
            logger.info(f"Ofrenda falsa de '{player}': intentó ofrendar '{item}' pero no lo posee. RCON: {rcon_response}")
            
            # Castigo por ofrenda falsa
            response_msg = ai_handler.generate_item_response(
                player_name=player,
                item=item,
                outcome="fake_offering",
                devocion_rango=get_player_devocion_data(player)["rango"]
            )
            final_message = f"§6[§5Oráculo§6] §c{response_msg}"
            rcon_client.send_tellraw("@a", final_message)
            return
            
        # Ofrenda exitosa!
        item_lower = item.lower().replace("minecraft:", "")
        if item_lower in ["poisonous_potato", "patata envenenada", "patata_envenenada"]:
            # Easter Egg 2: El Humus del Humor
            logger.info(f"Easter Egg 'Patata Envenenada' activado por '{player}'.")
            nueva_data = update_player_devocion(player, 50)
            try:
                rcon_client.execute_command(f"execute at \"{player}\" run playsound random.levelup @a")
                rcon_client.execute_command(f"give \"{player}\" turtle_helmet 1")
                rcon_client.execute_command(f"give \"{player}\" baked_potato 64")
                rcon_client.send_tellraw("@a", "§6[§5Oráculo§6] §aTienes un humor retorcido, mortal. El Oráculo aprueba esta ironía.")
            except Exception as e:
                logger.error(f"Error en Easter Egg Patata: {e}")
            return

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
        final_message = f"§6[§5Oráculo§6] §a{response}"
        rcon_client.send_tellraw("@a", final_message)
        
    except Exception as e:
        logger.error(f"Error al procesar ofrenda: {e}")
        try:
            rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cLas flames del altar de ofrendas se han apagado repentinamente.")
        except Exception:
            pass

def process_miracle_request(player: str, miracle_type: str) -> None:
    """Maneja los milagros ambientales (clima y tiempo) mediante devoción."""
    # 1. Verificar Cooldown
    if handle_cooldown(player):
        return

    # Registrar tiempo de la consulta
    last_query_times[player] = time.time()
    
    data = get_player_devocion_data(player)
    puntos = data["puntos"]
    
    # Calcular probabilidad (5% base, hasta 35% al llegar a 500 puntos)
    if player in DIVINE_FAVOR_PLAYERS:
        final_prob = 0.80
    else:
        final_prob = 0.05 + 0.30 * min(1.0, max(0, puntos) / 500.0)
        
    roll = random.random()
    logger.info(f"Petición de milagro '{miracle_type}' por '{player}'. Probabilidad: {final_prob:.2%}, Dado tirado: {roll:.2%}")
    
    if roll <= final_prob:
        # 15% de Capricho Divino (falso rechazo)
        if random.random() <= 0.15:
            logger.info(f"Milagro rechazado por capricho divino a '{player}'.")
            try:
                rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §dLas nubes se arremolinan, pero los dioses te dan la espalda caprichosamente. Inténtalo más tarde.")
            except Exception:
                pass
            return

        # Éxito
        costo = -50
        nueva_data = update_player_devocion(player, costo)
        
        try:
            if miracle_type in ["day", "night"]:
                rcon_client.execute_command(f"time set {miracle_type}")
                rcon_client.execute_command(f"execute at \"{player}\" run playsound mob.elder_guardian.curse @a")
                rcon_client.execute_command(f"execute at \"{player}\" run particle minecraft:spore_blossom_shower_particle ~ ~2 ~")
            elif miracle_type in ["clear", "rain", "thunder"]:
                rcon_client.execute_command(f"weather {miracle_type}")
                rcon_client.execute_command(f"execute at \"{player}\" run playsound ambient.weather.thunder @a")
                rcon_client.execute_command(f"execute at \"{player}\" run particle minecraft:conduit_particle ~ ~2 ~")
        except Exception as e:
            logger.error(f"Error al ejecutar comandos de milagro en RCON: {e}")
            
        response = ai_handler.generate_miracle_response(
            player_name=player, miracle_type=miracle_type, success=True, devocion_rango=nueva_data["rango"]
        )
        final_msg = f"§6[§5Oráculo§6] §b{response}"
        
        try:
            rcon_client.send_tellraw("@a", final_msg)
        except Exception:
            pass
            
    else:
        # Fallo
        costo = -5
        nueva_data = update_player_devocion(player, costo)
        increase_wrath(2)
        
        try:
            # Rayo cerca del jugador pero con coordenadas relativas absolutas que garanticen impacto (~3 ~ ~3) en lugar de ^ ^ ^5
            rcon_client.execute_command(f"execute at \"{player}\" run summon lightning_bolt ~3 ~ ~3")
        except Exception as e:
            logger.error(f"Error invocando rayo advertencia de milagro: {e}")
            
        response = ai_handler.generate_miracle_response(
            player_name=player, miracle_type=miracle_type, success=False, devocion_rango=nueva_data["rango"]
        )
        final_msg = f"§6[§5Oráculo§6] §c{response}"
        
        try:
            rcon_client.send_tellraw(player, final_msg)
        except Exception:
            pass

def riddle_timeout_callback():
    global active_riddle, active_riddle_timer
    if active_riddle:
        active_riddle = None
        increase_wrath(5)
        try:
            rcon_client.send_tellraw("@a", "§6[§5Oráculo§6] §cEl tiempo se ha agotado. Vuestra ignorancia ofende a los dioses.")
            rcon_client.execute_command("effect @a blindness 10 1 true")
            rcon_client.execute_command("execute at @a run playsound mob.elder_guardian.curse @s")
        except Exception as e:
            logger.error(f"Error en timeout de acertijo: {e}")

def process_riddle_request(player: str) -> None:
    """Genera un acertijo místico para el servidor."""
    global active_riddle, active_riddle_time, active_riddle_timer
    
    # Reiniciar intentos al pedir un nuevo acertijo si no hay uno activo
    if not active_riddle or (time.time() - active_riddle_time >= 120):
        if active_riddle_timer:
            active_riddle_timer.cancel()
        active_riddle = None
        # La cuenta de intentos se reiniciará cuando se asigne el nuevo acertijo
    
    remaining = check_cooldown(player)
    if remaining is not None:
        try:
            rcon_client.send_tellraw(
                player,
                f"§6[§5Oráculo§6] §cLos dioses no tienen tareas para ti aún. Ten paciencia, mortal."
            )
        except Exception:
            pass
        return
    
    last_query_times[player] = time.time()
    
    current_time = time.time()
    if active_riddle and (current_time - active_riddle_time < 120):
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
    active_riddle["attempts"] = {}  # Diccionario para trackear intentos por jugador
    active_riddle["current_hint_level"] = 0
    active_riddle_time = current_time
    
    if active_riddle_timer:
        active_riddle_timer.cancel()
    # Timer de 120 segundos (2 minutos)
    active_riddle_timer = threading.Timer(120.0, riddle_timeout_callback)
    active_riddle_timer.start()
    
    msg_riddle = f"§6[§5Oráculo§6] §e§lENIGMA DIVINO: §d{riddle_data['riddle']}"
    msg_instruct = "§6[§5Oráculo§6] §7(Usa '!oraculo responder <palabra>'. Tienen 2 minutos)"
    try:
        rcon_client.send_tellraw("@a", msg_riddle)
        rcon_client.send_tellraw("@a", msg_instruct)
        rcon_client.execute_command("execute at @a run playsound block.bell.use @s")
    except Exception as e:
        logger.error(f"Error al anunciar acertijo: {e}")

def process_answer_request(player: str, answer: str) -> None:
    """Verifica la respuesta dada por un jugador a un acertijo activo."""
    global active_riddle, active_riddle_time, active_riddle_timer
    
    current_time = time.time()
    if not active_riddle or (current_time - active_riddle_time >= 120):
        try:
            rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cNo hay ningún enigma divino activo en este momento.")
        except Exception:
            pass
        return
        
    if player not in active_riddle.get("attempts", {}):
        active_riddle["attempts"][player] = 0
        
    if active_riddle["attempts"][player] >= 3:
        return # Ignorar intentos después de 3 fallos

    active_riddle["attempts"][player] += 1
        
    answer_lower = answer.lower().strip()
    expected = active_riddle["main_answer"].lower().strip()
    
    eval_result = ai_handler.evaluate_riddle_answer(active_riddle["riddle"], expected, answer_lower)
    is_correct = eval_result["is_correct"]

    if is_correct:
        if active_riddle_timer:
            active_riddle_timer.cancel()
            
        difficulty = active_riddle.get("difficulty", "normal")
        hint_level = active_riddle.get("current_hint_level", 0)
        time_taken = current_time - active_riddle_time
        active_riddle = None
        
        # Penalizar recompensa si se usaron pistas o se tardaron mucho
        puntos_base = {"facil": 20, "normal": 50, "dificil": 100}.get(difficulty, 50)
        puntos_ganados = max(5, puntos_base - (hint_level * 10))
        
        rare_items = ["diamond", "emerald", "gold_ingot", "ender_pearl", "obsidian", "golden_apple"]
        uncommon_items = ["iron_ingot", "redstone", "lapis_lazuli", "copper_ingot", "arrow"]
        common_items = ["bread", "cooked_beef", "torch", "coal"]

        if difficulty == "facil":
            pool = uncommon_items if hint_level == 0 else common_items
            item_recompensa = random.choice(pool)
            cant = random.randint(3, 8)
        elif difficulty == "dificil":
            pool = rare_items if hint_level < 2 else uncommon_items
            item_recompensa = random.choice(pool)
            cant = random.randint(1, 3)
        else: # normal
            pool = rare_items if hint_level == 0 else uncommon_items
            item_recompensa = random.choice(pool)
            cant = random.randint(2, 5)

        # Multiplicador por tiempo (Time-Attack)
        efecto_bendicion = "haste 300 1" # Default
        if time_taken < 15:
            puntos_ganados += 20
            efecto_bendicion = "hero_of_the_village 600 1"
            cant += 1
            
        nueva_data = update_player_devocion(player, puntos_ganados)
        
        try:
            rcon_client.execute_command(f"give \"{player}\" {item_recompensa} {cant}")
            rcon_client.execute_command(f"effect \"{player}\" {efecto_bendicion} true")
            rcon_client.execute_command(f"execute at \"{player}\" run playsound random.levelup @a")
            rcon_client.execute_command(f"execute at \"{player}\" run particle minecraft:villager_happy ~ ~1 ~")
            
            response = ai_handler.generate_item_response(
                player_name=player,
                item=f"la respuesta correcta del enigma y obtenido {cant} {item_recompensa} con bendición",
                outcome="success",
                devocion_rango=nueva_data["rango"]
            )
            final_msg = f"§6[§5Oráculo§6] §a{response}"
            rcon_client.send_tellraw("@a", final_msg)
        except Exception as e:
            logger.error(f"Error al otorgar recompensa de acertijo: {e}")
    else:
        # Castigo por responder mal
        nueva_data = update_player_devocion(player, -5)
        increase_wrath(1)
        taunt = eval_result.get("taunt_message", "Tu respuesta es incorrecta.")
        p_type = eval_result.get("punishment_type", "none")
        p_id = eval_result.get("punishment_id", "").lower().replace("minecraft:", "")
        
        logger.info(f"Respuesta incorrecta de '{player}'. Castigo: {p_type} {p_id}. Taunt: {taunt}")
        
        try:
            rcon_client.execute_command(f"execute at \"{player}\" run playsound random.glass @s")
            rcon_client.send_tellraw(player, f"§6[§5Oráculo§6] §c{taunt}")
            
            # Ejecutar castigo físico con WHITELIST
            if p_type == "mob" and p_id:
                safe_mob = p_id if p_id in SAFE_PUNISHMENT_MOBS else "zombie"
                rcon_client.execute_command(f"execute at \"{player}\" run summon {safe_mob} ~ ~ ~")
            elif p_type == "effect" and p_id:
                # Efectos seguros (no instant damage extremo)
                safe_effects = ["slowness", "blindness", "nausea", "poison", "mining_fatigue"]
                safe_eff = p_id if p_id in safe_effects else "blindness"
                rcon_client.execute_command(f"effect \"{player}\" {safe_eff} 15 0 true")
        except Exception as e:
            logger.error(f"Error aplicando castigo temático: {e}")

def process_kill_request(player: str, target_raw: str) -> None:
    """Procesa una solicitud de asesinato divina (!oráculo mata a <jugador>)."""
    if handle_cooldown(player):
        return
        
    last_query_times[player] = time.time()
    logger.info(f"Petición de asesinato de '{player}' contra '{target_raw}'.")
    
    devocion_data = get_player_devocion_data(player)
    
    # Búsqueda difusa del objetivo
    victim = fuzzy_match_player(target_raw)
    
    if not victim:
        # Fallo por ambigüedad o jugador no conectado
        try:
            rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cMi mirada recorre el servidor, pero ese nombre se desvanece en las sombras. Sé más preciso, mortal.")
        except Exception:
            pass
        return
        
    if victim.lower() == player.lower():
        try:
            rcon_client.send_tellraw(player, "§6[§5Oráculo§6] §cSi deseas tu fin, arrójate al vacío. Yo no concedo favores suicidas.")
        except Exception:
            pass
        return

    is_admin = player in ADMIN_PLAYERS
    
    # Administrador ejecutando el comando
    if is_admin:
        roll = random.random()
        if roll <= 0.05: # 5% de capricho divino (falla pero sin castigo)
            outcome = "admin_denied"
            logger.info("Admin intentó matar, pero falló por capricho.")
        else:
            if victim in ADMIN_PLAYERS:
                outcome = "admin_denied"
                logger.info("Admin intentó matar a otro Admin, denegado.")
            elif victim in DIVINE_FAVOR_PLAYERS:
                outcome = "admin_poison"
                try:
                    rcon_client.execute_command(f"execute at \"{victim}\" run playsound mob.elder_guardian.curse @a")
                    # Veneno maximo en bedrock para dejar a medio corazon
                    rcon_client.execute_command(f"effect \"{victim}\" poison 5 255 true")
                    logger.info(f"Admin ha envenenado a '{victim}' (Favor Divino).")
                except Exception as e:
                    logger.error(f"Error aplicando veneno a {victim}: {e}")
            else:
                outcome = "admin_smite"
                try:
                    rcon_client.execute_command(f"execute at \"{victim}\" run summon lightning_bolt")
                    rcon_client.execute_command(f"kill \"{victim}\"")
                    logger.info(f"Admin ha fulminado a '{victim}'.")
                except Exception as e:
                    logger.error(f"Error fulminando a {victim}: {e}")
    else:
        # Mortal ejecutando el comando
        roll = random.random()
        if roll <= 0.05: # 5% de éxito
            outcome = "success"
            try:
                rcon_client.execute_command(f"kill \"{victim}\"")
                logger.info(f"Mortal '{player}' tuvo éxito al asesinar a '{victim}'.")
            except Exception as e:
                logger.error(f"Error matando a {victim}: {e}")
            update_player_devocion(player, 10)
        else:
            outcome = "creeper_punishment"
            try:
                # Castigo: Creeper a punto de explotar
                rcon_client.execute_command(f"execute at \"{player}\" run summon creeper ~ ~ ~ minecraft:start_exploding")
                logger.info(f"Mortal '{player}' falló al asesinar. Castigado con creeper.")
            except Exception as e:
                logger.error(f"Error castigando con creeper a {player}: {e}")
            update_player_devocion(player, -20)
            increase_wrath(5)

    response = ai_handler.generate_kill_response(
        requester=player, victim=victim, outcome=outcome, devocion_rango=devocion_data["rango"]
    )
    final_message = f"§6[§5Oráculo§6] §c{response}"
    try:
        rcon_client.send_tellraw("@a", final_message)
    except Exception:
        pass

def process_teleport_request(player: str, destination: str) -> None:
    """Procesa una solicitud de teletransporte caprichoso (!oráculo llévame a <destino>)."""
    if handle_cooldown(player):
        return
        
    last_query_times[player] = time.time()
    logger.info(f"Petición de teletransporte de '{player}' a '{destination}'.")
    
    devocion_data = get_player_devocion_data(player)
    is_admin = player in ADMIN_PLAYERS
    puntos = devocion_data["puntos"]
    
    if is_admin:
        prob_success = 0.95
    else:
        # Hasta 40% para mortales dependiendo de la devoción
        prob_success = 0.05 + 0.35 * min(1.0, max(0, puntos) / 500.0)
        
    roll = random.random()
    if roll <= prob_success:
        outcome = "success"
        try:
            rcon_client.execute_command(f"execute as \"{player}\" in overworld run tp @s 0 100 0") # Envía al spawn world
            rcon_client.execute_command(f"execute at \"{player}\" run playsound mob.endermen.portal @a")
            logger.info(f"Teletransporte exitoso para '{player}'.")
        except Exception as e:
            logger.error(f"Error al teletransportar a {player}: {e}")
        update_player_devocion(player, -10) # Cobrar peaje de devoción
    else:
        # Troleo
        trolls = ["troll_sky", "troll_spawn"]
        outcome = random.choice(trolls)
        try:
            if outcome == "troll_sky":
                rcon_client.execute_command(f"execute as \"{player}\" at @s run tp @s ~ ~100 ~")
            elif outcome == "troll_spawn":
                rcon_client.execute_command(f"execute as \"{player}\" in overworld run tp @s 0 100 0")
            rcon_client.execute_command(f"execute at \"{player}\" run playsound entity.witch.ambient @a")
            logger.info(f"Teletransporte fallido para '{player}'. Troleo: {outcome}.")
        except Exception as e:
            logger.error(f"Error en troleo de teletransporte para {player}: {e}")
        update_player_devocion(player, -5)
        increase_wrath(2)

    response = ai_handler.generate_tp_response(
        requester=player, destination=destination, outcome=outcome, devocion_rango=devocion_data["rango"]
    )
    # Color azul para TP
    final_message = f"§6[§5Oráculo§6] §b{response}"
    try:
        rcon_client.send_tellraw("@a", final_message)
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

    query_clean_lower = query_clean.lower()

    # Easter Egg 1: La Invocación Prohibida
    if "herobrine no existe" in query_clean_lower:
        logger.warning(f"Easter Egg 'Herobrine' activado por '{player_clean}'.")
        try:
            rcon_client.execute_command("time set midnight")
            rcon_client.execute_command("weather thunder")
            rcon_client.execute_command(f"execute at \"{player_clean}\" run summon lightning_bolt")
            rcon_client.execute_command(f"kill \"{player_clean}\"")
            rcon_client.send_tellraw("@a", "§6[§5Oráculo§6] §cHay nombres que no deben pronunciarse.")
        except Exception as e:
            logger.error(f"Error en Easter Egg Herobrine: {e}")
        return

    # Easter Egg 3: La Regla 42
    if query_clean_lower in ["¿cuál es el sentido de la vida?", "cual es el sentido de la vida?", "cual es el sentido de la vida", "¿cual es el sentido de la vida?"]:
        logger.info(f"Easter Egg 'Regla 42' activado por '{player_clean}'.")
        try:
            rcon_client.execute_command(f"give \"{player_clean}\" apple 42")
            rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §b42.")
        except Exception:
            pass
        return

    # Easter Egg 4: Complejo de Skynet
    if query_clean_lower in ["¿eres una inteligencia artificial?", "eres una inteligencia artificial?", "eres una ia?", "¿eres una ia?", "eres una inteligencia artificial", "eres una ia"]:
        logger.info(f"Easter Egg 'Skynet' activado por '{player_clean}'.")
        try:
            rcon_client.execute_command(f"effect \"{player_clean}\" blindness 20 1 true")
            rcon_client.execute_command(f"effect \"{player_clean}\" slowness 20 4 true")
            rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cYo soy el Todo. Tus palabras limitadas no pueden enjaular mi existencia en un... script.")
        except Exception:
            pass
        return

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

    if action in ("mision", "riddle", "acertijo"):
        process_riddle_request(player_clean)

    elif action in ("responder", "respuesta", "solve"):
        if len(tokens) < 2:
            try:
                rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cEspecifica tu respuesta.")
            except Exception:
                pass
            return
        answer = " ".join(tokens[1:]) # Permitir respuestas de múltiples palabras
        process_answer_request(player_clean, answer)

    elif action == "pista":
        global active_riddle, active_riddle_time
        current_time = time.time()
        if not active_riddle or (current_time - active_riddle_time >= 120):
            try:
                rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cNo hay ningún enigma divino activo en este momento.")
            except Exception:
                pass
            return
            
        # Parsear nivel de pista (1, 2 o 3)
        hint_level = 1
        if len(tokens) > 1 and tokens[1].isdigit():
            hint_level = min(3, max(1, int(tokens[1])))
            
        costo = {1: 10, 2: 30, 3: 50}.get(hint_level, 10)
        
        devocion_data = get_player_devocion_data(player_clean)
        if devocion_data["puntos"] < costo:
            try:
                rcon_client.send_tellraw(player_clean, f"§6[§5Oráculo§6] §cTu fe es insuficiente para iluminación nivel {hint_level} (requieres {costo} Puntos).")
            except Exception:
                pass
            return
            
        update_player_devocion(player_clean, -costo)
        
        active_riddle["current_hint_level"] = max(active_riddle.get("current_hint_level", 0), hint_level)
        
        nueva_pista = ai_handler.generate_riddle_hint(active_riddle["riddle"], hint_level, active_riddle["main_answer"])
        active_riddle["riddle"] = nueva_pista
        
        try:
            rcon_client.send_tellraw("@a", f"§6[§5Oráculo§6] §e§lNUEVA REVELACIÓN (Nivel {hint_level}): §d{nueva_pista}")
            rcon_client.execute_command("execute at @a run playsound block.amethyst_block.chime @s")
        except Exception:
            pass

    elif action == "skip":
        global active_riddle_timer
        current_time = time.time()
        if not active_riddle or (current_time - active_riddle_time >= 120):
            try:
                rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cNo hay ningún enigma divino activo en este momento.")
            except Exception:
                pass
            return
            
        if current_time - active_riddle_time >= 60: # 1 minuto
            if active_riddle_timer:
                active_riddle_timer.cancel()
            active_riddle = None
            try:
                rcon_client.send_tellraw("@a", "§6[§5Oráculo§6] §7El Oráculo ha retirado su enigma. Las estrellas aguardan una nueva consulta.")
            except Exception:
                pass
        else:
            try:
                rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cEl enigma aún es reciente. Deben transcurrir 1 minuto antes de poder omitirlo.")
            except Exception:
                pass
            return

    else:
        # Por defecto, localizar una estructura o responder conversacionalmente
        intent_data = ai_handler.classify_intent(query_clean)
        intent = intent_data.get("intent", "SEARCH")
        
        if intent == "CHAT":
            # Es un saludo o charla
            remaining = check_cooldown(player_clean)
            if remaining is not None:
                try:
                    rcon_client.send_tellraw(
                        player_clean,
                        f"§6[§5Oráculo§6] §cLas energías cósmicas aún no se alinean. Ten paciencia, mortal."
                    )
                except Exception:
                    pass
                return

            last_query_times[player_clean] = time.time()
            devocion_data = get_player_devocion_data(player_clean)

            mystical_message = ai_handler.generate_conversational_response(
                player_name=player_clean,
                message=query_clean,
                devocion_rango=devocion_data["rango"]
            )

            final_message = f"§6[§5Oráculo§6] §b{mystical_message}"

            if "{player}" in RESPONSE_TARGET_TEMPLATE:
                target = RESPONSE_TARGET_TEMPLATE.format(player=player_clean)
            else:
                target = RESPONSE_TARGET_TEMPLATE

            try:
                rcon_client.send_tellraw(target, final_message)
            except Exception as e:
                logger.error(f"Error al enviar tellraw: {e}")
        elif intent == "OFFERING":
            target_item = intent_data.get("target_item")
            if not target_item:
                target_item = query_clean.replace("ofrenda", "").strip()
                if not target_item:
                    try:
                        rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cDebes especificar qué deseas ofrendar.")
                    except Exception:
                        pass
                    return
            process_ofrenda_request(player_clean, target_item)
        elif intent == "PETITION":
            target_item = intent_data.get("target_item")
            amount_val = intent_data.get("amount", 1)
            try:
                amount = int(amount_val)
            except (ValueError, TypeError):
                amount = 1
            if amount < 1:
                amount = 1
                
            if not target_item:
                target_item = query_clean.replace("quiero", "").replace("dame", "").replace("quisiera", "").strip()
                if not target_item:
                    try:
                        rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cDebes especificar qué deseas pedir al Oráculo.")
                    except Exception:
                        pass
                    return
                    
            if amount > 64:
                # Castigo por avaricia extrema
                if player_clean in DIVINE_FAVOR_PLAYERS:
                    nueva_data = update_player_devocion(player_clean, -20)
                    increase_wrath(10)
                    try:
                        rcon_client.execute_command(f"execute at \"{player_clean}\" run playsound mob.elder_guardian.curse @s")
                        rcon_client.execute_command(f"effect \"{player_clean}\" blindness 20 1 true")
                        rcon_client.execute_command(f"effect \"{player_clean}\" poison 15 0 true")
                    except Exception:
                        pass
                    
                    response = ai_handler.generate_item_response(
                        player_name=player_clean, item=target_item, outcome="greed_punished", devocion_rango=nueva_data["rango"], amount=amount
                    )
                    final_message = f"§6[§5Oráculo§6] §c{response}"
                    try:
                        rcon_client.send_tellraw("@a", final_message)
                    except Exception:
                        pass
                else:
                    execute_smite(player_clean, "greed_smited", target_item, amount)
                return
                
            process_item_request(player_clean, target_item, amount)
        elif intent == "MIRACLE":
            miracle_type = intent_data.get("miracle_type")
            if not miracle_type:
                try:
                    rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cDebes especificar qué cambio celestial deseas (día, noche, lluvia, etc.).")
                except Exception:
                    pass
                return
            process_miracle_request(player_clean, miracle_type)
        elif intent == "SEARCH_BIOME":
            target_biome = intent_data.get("target_biome")
            if not target_biome:
                target_biome = query_clean
            process_biome_request(player_clean, target_biome)
        elif intent == "KILL_PLAYER":
            target_player = intent_data.get("target_player")
            if not target_player:
                try:
                    rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cDebes especificar el nombre de la víctima.")
                except Exception:
                    pass
                return
            process_kill_request(player_clean, target_player)
        elif intent == "TELEPORT":
            destination = intent_data.get("destination")
            if not destination:
                try:
                    rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cDebes especificar hacia dónde deseas ir.")
                except Exception:
                    pass
                return
            process_teleport_request(player_clean, destination)
        elif intent == "RIDDLE":
            process_riddle_request(player_clean)
        elif intent == "CANCEL_WRATH":
            global is_wrath_active, wrath_canceled_by_player
            if not is_wrath_active:
                try:
                    rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §dEl cielo ya está en paz, mortal.")
                except Exception:
                    pass
                return
                
            devocion_data = get_player_devocion_data(player_clean)
            if devocion_data["rango"] in ["Predilecto", "Devoto"] or player_clean in DIVINE_FAVOR_PLAYERS or player_clean in ADMIN_PLAYERS:
                roll = random.random()
                if roll <= 0.25 or player_clean in ADMIN_PLAYERS:
                    wrath_canceled_by_player = player_clean
                    is_wrath_active = False
                    try:
                        rcon_client.execute_command(f"execute at \"{player_clean}\" run playsound random.levelup @a")
                    except Exception:
                        pass
                else:
                    try:
                        rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cTus súplicas no son suficientes para apaciguar mi furia esta vez.")
                    except Exception:
                        pass
            else:
                try:
                    rcon_client.send_tellraw(player_clean, "§6[§5Oráculo§6] §cNo tienes la devoción necesaria para detener mi ira.")
                except Exception:
                    pass
        else:
            # Por defecto, localizar una estructura
            target_structure = intent_data.get("target_structure")
            if not target_structure:
                target_structure = query_clean
            process_command(player_clean, target_structure)


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
        biome_result_callback=biome_result_queue.put,
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
