"""
Desactiva todos los experimentos (Beta APIs, Holiday Creator Features, etc.)
en el level.dat de un mundo de Minecraft Bedrock.

Desde BDS 1.26.30, los mundos con experimentos activos pueden impedir que los
jugadores se conecten ("Unable to join external servers", ver BDS-23063 y
MCPE-239705). Una vez activado un experimento, el juego no permite apagarlo
desde la interfaz, así que hay que editar el level.dat.

Uso (con el servidor APAGADO):
    python tools/desactivar_experimentos.py "/ruta/a/worlds/Mi Mundo"
    python tools/desactivar_experimentos.py "/ruta/a/worlds/Mi Mundo" --dry-run

Antes de escribir se guarda una copia en level.dat.bak-<fecha>.
Ojo: los add-ons que dependan de Beta APIs dejarán de funcionar.
"""

import argparse
import datetime
import os
import shutil
import struct
import sys

# Formatos little-endian de los tags NBT de tamaño fijo
_FIXED = {1: "<b", 2: "<h", 3: "<i", 4: "<q", 5: "<f", 6: "<d"}
_ARRAYS = {7: "<b", 11: "<i", 12: "<q"}
TAG_STRING, TAG_LIST, TAG_COMPOUND = 8, 9, 10


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def unpack(self, fmt: str):
        value = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += struct.calcsize(fmt)
        return value

    def string(self) -> str:
        length = self.unpack("<H")
        raw = self.data[self.pos:self.pos + length]
        self.pos += length
        return raw.decode("utf-8")

    def payload(self, tag_type: int):
        if tag_type in _FIXED:
            return self.unpack(_FIXED[tag_type])
        if tag_type in _ARRAYS:
            return [self.unpack(_ARRAYS[tag_type]) for _ in range(self.unpack("<i"))]
        if tag_type == TAG_STRING:
            return self.string()
        if tag_type == TAG_LIST:
            item_type = self.unpack("<b")
            return (item_type, [self.payload(item_type) for _ in range(self.unpack("<i"))])
        if tag_type == TAG_COMPOUND:
            entries = []
            while True:
                child_type = self.unpack("<b")
                if child_type == 0:
                    return entries
                name = self.string()
                entries.append([child_type, name, self.payload(child_type)])
        raise ValueError(f"Tipo de tag NBT desconocido: {tag_type}")


def _write_string(out: bytearray, text: str) -> None:
    raw = text.encode("utf-8")
    out += struct.pack("<H", len(raw)) + raw


def _write_payload(out: bytearray, tag_type: int, value) -> None:
    if tag_type in _FIXED:
        out += struct.pack(_FIXED[tag_type], value)
    elif tag_type in _ARRAYS:
        out += struct.pack("<i", len(value))
        for item in value:
            out += struct.pack(_ARRAYS[tag_type], item)
    elif tag_type == TAG_STRING:
        _write_string(out, value)
    elif tag_type == TAG_LIST:
        item_type, items = value
        out += struct.pack("<bi", item_type, len(items))
        for item in items:
            _write_payload(out, item_type, item)
    elif tag_type == TAG_COMPOUND:
        for child_type, name, child in value:
            out += struct.pack("<b", child_type)
            _write_string(out, name)
            _write_payload(out, child_type, child)
        out += b"\x00"
    else:
        raise ValueError(f"Tipo de tag NBT desconocido: {tag_type}")


def read_level_dat(path: str):
    """Devuelve (version_de_almacenamiento, nombre_raiz, compound_raiz)."""
    data = open(path, "rb").read()
    version, length = struct.unpack_from("<ii", data, 0)
    reader = _Reader(data[8:8 + length])
    root_type = reader.unpack("<b")
    if root_type != TAG_COMPOUND:
        raise ValueError("level.dat no empieza con un compound NBT")
    root_name = reader.string()
    return version, root_name, reader.payload(TAG_COMPOUND)


def serialize_level_dat(version: int, root_name: str, root) -> bytes:
    body = bytearray(struct.pack("<b", TAG_COMPOUND))
    _write_string(body, root_name)
    _write_payload(body, TAG_COMPOUND, root)
    return struct.pack("<ii", version, len(body)) + bytes(body)


def disable_experiments(root) -> list:
    """Pone en 0 cada experimento activo. Devuelve los nombres modificados."""
    changed = []
    for tag_type, name, value in root:
        if name == "experiments" and tag_type == TAG_COMPOUND:
            for entry in value:
                if entry[0] == 1 and entry[2] != 0:
                    changed.append(entry[1])
                    entry[2] = 0
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mundo", help="Carpeta del mundo (la que contiene level.dat)")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar qué se cambiaría")
    args = parser.parse_args()

    path = os.path.join(args.mundo, "level.dat")
    if not os.path.isfile(path):
        print(f"No se encontró {path}")
        return 1

    version, root_name, root = read_level_dat(path)
    original = open(path, "rb").read()
    if serialize_level_dat(version, root_name, root) != original:
        print("El level.dat no se pudo releer de forma idéntica; no se modificará por seguridad.")
        return 1

    experiments = next((v for t, n, v in root if n == "experiments" and t == TAG_COMPOUND), [])
    print("Experimentos actuales:")
    for tag_type, name, value in experiments:
        print(f"  {name} = {value}")

    changed = disable_experiments(root)
    if not changed:
        print("No hay experimentos activos. Nada que hacer.")
        return 0
    print(f"Se desactivarán: {', '.join(changed)}")
    if args.dry_run:
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.bak-{stamp}"
    shutil.copy2(path, backup)
    with open(path, "wb") as f:
        f.write(serialize_level_dat(version, root_name, root))
    print(f"Listo. Copia de seguridad en: {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
