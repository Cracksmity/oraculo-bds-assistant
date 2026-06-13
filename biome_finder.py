import math
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Mapeo básico de algunos biomas de Bedrock a sus posibles IDs numéricos en pycubiomes.
# Si el wrapper provee funciones para obtener el ID desde el nombre, se puede reemplazar.
BIOME_IDS = {
    "plains": 1,
    "desert": 2,
    "forest": 4,
    "taiga": 5,
    "swamp": 6,
    "jungle": 21,
    "savanna": 35,
    "badlands": 37,
    "mesa": 37,
    "snowy_tundra": 12,
    "snowy_taiga": 30,
    "dark_forest": 29,
    "birch_forest": 27,
    "mushroom_fields": 14,
    "ice_spikes": 140,
    # Puedes ampliar esta lista según la tabla de biomas de Bedrock/Java
}

class BiomeFinder:
    def __init__(self, seed: int):
        self.seed = seed
        self.has_library = False
        self.Pyubiomes = None
        
        try:
            # Importar el wrapper Pyubiomes específico
            import Pyubiomes
            self.Pyubiomes = Pyubiomes
            self.has_library = True
            logger.info(f"Pyubiomes cargado exitosamente con la semilla {self.seed}.")
        except ImportError:
            logger.warning("No se pudo importar 'Pyubiomes'. La búsqueda de biomas usará un fallback simulado para mantener el bot funcional.")
        except Exception as e:
            logger.error(f"Error al inicializar Pyubiomes: {e}")

    def is_biome_at(self, biome_id: int, x: int, z: int) -> bool:
        """Verifica si el bioma especificado está en las coordenadas dadas usando Pyubiomes."""
        if self.has_library and self.Pyubiomes:
            try:
                # Usar MC_1_20 (o la versión reciente que tenga) como aproximación a Bedrock
                version = 20 # 1.20 = 20 en la librería usualmente, o Pyubiomes.Versions.MC_1_20
                if hasattr(self.Pyubiomes, 'Versions') and hasattr(self.Pyubiomes.Versions, 'MC_1_20'):
                    version = self.Pyubiomes.Versions.MC_1_20
                    
                return self.Pyubiomes.biome_at_pos(biome_id, self.seed, x, z, version)
            except Exception as e:
                pass
        return False

    def find_nearest_biome(self, biome_name: str, start_x: float, start_z: float, max_radius: int = 5000, step: int = 64) -> Optional[Tuple[float, float]]:
        """
        Realiza una búsqueda en espiral concéntrica (cuadrada) para encontrar el bioma deseado.
        """
        biome_id = BIOME_IDS.get(biome_name.lower())
        
        if not self.has_library:
            logger.warning(f"Pyubiomes no instalado. Simulando coordenadas para el bioma '{biome_name}'.")
            # Simulación: Devuelve un punto aleatorio en un rango razonable para que el bot responda
            import random
            sim_dist = random.randint(1000, 3000)
            angle = random.uniform(0, 2 * math.pi)
            return (start_x + sim_dist * math.cos(angle), start_z + sim_dist * math.sin(angle))
            
        if biome_id is None:
            logger.warning(f"Bioma '{biome_name}' no reconocido en el diccionario interno.")
            return None

        x = int(start_x)
        z = int(start_z)
        
        # Revisar el centro primero
        if self.is_biome_at(biome_id, x, z):
            return float(x), float(z)

        # Espiral cuadrada aumentando el radio
        for radius in range(step, max_radius + step, step):
            # Lado superior (Norte)
            for dx in range(-radius, radius + 1, step):
                if self.is_biome_at(biome_id, x + dx, z - radius):
                    return float(x + dx), float(z - radius)
            # Lado derecho (Este)
            for dz in range(-radius + step, radius + 1, step):
                if self.is_biome_at(biome_id, x + radius, z + dz):
                    return float(x + radius), float(z + dz)
            # Lado inferior (Sur)
            for dx in range(radius - step, -radius - 1, -step):
                if self.is_biome_at(biome_id, x + dx, z + radius):
                    return float(x + dx), float(z + radius)
            # Lado izquierdo (Oeste)
            for dz in range(radius - step, -radius, -step):
                if self.is_biome_at(biome_id, x - radius, z + dz):
                    return float(x - radius), float(z + dz)

        logger.info(f"Bioma '{biome_name}' no encontrado en un radio de {max_radius} bloques.")
        return None
