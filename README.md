# 👁️ Oráculo BDS Assistant

> [!IMPORTANT]
> **Compatible con BDS 1.26.30+ desde la v1.1.0.** La versión anterior dependía de `@minecraft/server-net`, que solo existe como API Beta. Desde BDS 1.26.30, los mundos con experimentos activos (Beta APIs) dejan a los jugadores atascados en *"Connecting to the server"* / *"Unable to join external servers"* ([BDS-23063](https://mojira.dev/BDS-23063), [MCPE-239705](https://mojira.dev/MCPE-239705)). El puente ahora usa **solo APIs estables** y se comunica con Python a través de la consola del servidor, así que el mundo **ya no necesita ningún experimento**. Ver [Migración desde la v1.0.x](#-migración-desde-la-v10x).

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Minecraft](https://img.shields.io/badge/Minecraft%20Bedrock-Dedicated%20Server-green)
![OpenAI](https://img.shields.io/badge/AI-OpenAI-orange)

**Oráculo BDS Assistant** es un sistema de asistencia avanzado y misterioso impulsado por inteligencia artificial para servidores de Minecraft Bedrock (BDS). Diseñado con una arquitectura híbrida (Consola del BDS + OpenAI), este bot introduce una deidad interactiva en tu mundo: **El Oráculo**.

El Oráculo es capaz de entender lenguaje natural, juzgar las acciones de los jugadores, proponer acertijos, exigir sacrificios y, en última instancia, manipular el mismísimo clima y la vida en el servidor.

---

## ✨ Características Principales

*   **🗣️ Interacción Divina (OpenAI):** Respuestas inmersivas y místicas en el chat del juego. El Oráculo comprende el contexto y las intenciones de los jugadores mediante procesamiento de lenguaje natural.
*   **⚖️ Sistema de Devoción:** Cada jugador tiene un nivel de "favor" con los dioses. Completa pruebas o sé castigado según tus actos.
*   **🌪️ Ira Divina Global:** Evento apocalíptico para todo el servidor (rayos, ceguera, tormentas) que se desata al colmar la paciencia cósmica. Los devotos pueden detenerla mediante súplicas.
*   **🌍 Clarividencia de Biomas y Estructuras:** El Oráculo puede localizar biomas naturales y estructuras antiguas, guiándote con coordenadas relativas y rumbos místicos.
*   **⚖️ Castigo a la Avaricia y el Spam:** Pide ítems en cantidades específicas, pero cuidado: pedir más de un stack (avaricia) o insistir durante los tiempos de espera (spam) desatará advertencias y rayos mortales progresivos.
*   **🧩 Acertijos Mortales:** El Oráculo puede retar a los atrevidos. Respuestas correctas traen bendiciones (ítems raros, cielos despejados); los fallos invocan la ira divina (rayos, monstruos).
*   **🔥 Sacrificios y Ofrendas:** Arroja objetos valiosos frente al altar del Oráculo. La IA evalúa la rareza del ítem. Las ofrendas raras aumentan tu devoción; la basura te costará caro.
*   **⚡ Control Absoluto del Entorno (RCON):** Interacción directa con la consola de Minecraft. El Oráculo altera el tiempo (`/time`), el clima (`/weather`), otorga pociones específicas (`/give`) y castiga (`/summon`) sin intervención del administrador.

---

## 🏗️ Arquitectura del Sistema

El sistema opera en dos frentes que se comunican en tiempo real:

1.  **🧠 El Cerebro (Python - Servidor local/VPS):**
    Gestiona la lógica pesada, la IA y las respuestas.
    *   `main.py`: El corazón del sistema. Recibe los mensajes del Behavior Pack y ejecuta comandos en la consola del BDS.
    *   `console_bridge.py`: Lee el `server.log` y despacha las líneas `ORACULO_IPC::{json}` que escribe el Behavior Pack.
    *   `ai_handler.py`: Interfaz con OpenAI. Clasifica intenciones (charlas, clima, sacrificios, biomas) y moldea la personalidad del Oráculo.
    *   `biome_finder.py`: Sistema automatizado para el cálculo de distancias a biomas basado en la semilla del mundo.
    *   `rcon_client.py`: Puente asíncrono para inyectar comandos directamente en la consola del BDS.
    *   `devocion.db` (SQLite): Base de datos de jugadores que registra sus niveles de favor divino y progreso. Si existe `devocion.json`, se migra automáticamente al primer arranque.

2.  **👁️ Los Ojos y Oídos (JavaScript - Behavior Pack):**
    Ubicado en `oraculo_bridge/`. Se ejecuta dentro del mundo de Minecraft.
    *   Registra el comando `/oraculo <mensaje>` (API estable de comandos personalizados).
    *   Detecta conexiones de jugadores, ofrendas en el altar y valida el tamaño de biomas.
    *   Se comunica con Python escribiendo líneas `ORACULO_IPC::{json}` en la consola del servidor (sin HTTP ni Beta APIs).

---

## 🛠️ Requisitos e Instalación

### Requisitos Previos
*   Python 3.8 o superior.
*   Bedrock Dedicated Server (BDS) **1.21.120 o superior**, sin experimentos. El puente usa `@minecraft/server@2.3.0` (estable).
*   El BDS debe correr dentro de una sesión `screen` (Linux) y su salida debe guardarse en un archivo (`SERVER_LOG_FILE`). Bedrock no tiene RCON: el bot escribe los comandos en esa sesión y lee el log.
*   Una API Key válida de [OpenAI](https://platform.openai.com/).

### Instalación Paso a Paso

1.  **Clona o descarga este repositorio.**
2.  **Instala las dependencias de Python:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configura las Variables de Entorno:**
    Crea un archivo `.env` en la raíz (agrega tus credenciales). Este archivo es ignorado por seguridad:
    ```env
    # API Keys
    OPENAI_API_KEY=tu_api_key_aqui

    # Configuración del Servidor y Mundo
    WORLD_SEED=tu_semilla_del_mundo
    ADMIN_PLAYERS=tu_nombre_de_jugador
    DIVINE_FAVOR_PLAYERS=jugador_VIP1,jugador_VIP2

    # Consola del BDS
    SCREEN_SESSION_NAME=minecraft
    SERVER_LOG_FILE=/ruta/al/servidor/server.log
    ```
4.  **Instala el Behavior Pack:**
    *   Copia la carpeta `oraculo_bridge/` dentro de la carpeta `behavior_packs` de tu BDS.
    *   Agrega el pack en `worlds/<mundo>/world_behavior_packs.json` con `"version": [1, 1, 0]`. **No** actives ningún experimento.
5.  **Arranca el BDS guardando su salida en el log** (el `logfile flush 1` hace que el log se escriba casi al instante, el valor por defecto es cada 10 s):
    ```bash
    echo "logfile flush 1" >> ~/.screenrc
    screen -dmS minecraft -L -Logfile server.log ./bedrock_server
    ```
6.  **Despierta al Oráculo:**
    ```bash
    python main.py
    ```
7.  **En el juego**, cualquier jugador puede hablar con el Oráculo:
    ```
    /oraculo dame un acertijo
    /oraculo "¿dónde hay un bosque de cerezos?"
    ```
    Si el texto tiene signos raros y el juego marca error de sintaxis, ponlo entre comillas. Si otro addon ya usa `/oraculo`, escribe `/oraculo:oraculo`.

---

## 🔄 Migración desde la v1.0.x

1.  Reemplaza la carpeta `oraculo_bridge/` del servidor por la nueva y actualiza la versión en `world_behavior_packs.json` a `[1, 1, 0]`.
2.  Con el servidor **apagado**, desactiva los experimentos del mundo (el juego no permite apagarlos una vez activados). El script guarda una copia de seguridad del `level.dat`:
    ```bash
    python tools/desactivar_experimentos.py "/ruta/al/servidor/worlds/Mi Mundo" --dry-run
    python tools/desactivar_experimentos.py "/ruta/al/servidor/worlds/Mi Mundo"
    ```
    ⚠️ Cualquier otro addon que requiera Beta APIs dejará de funcionar.
3.  Ya no se usa `!oraculo` en el chat (el evento de chat sigue siendo Beta): ahora es `/oraculo <mensaje>`. El bot ya no abre un servidor HTTP; si por alguna razón sigues usando el pack viejo, pon `ENABLE_WEBHOOK=True` en el `.env`.

---

## 📚 Documentación y Secretos

Para más detalles sobre cómo personalizar al Oráculo, las reglas del sistema de Devoción y los **Misterios (Easter Eggs)** ocultos que puedes implementar en tu servidor, consulta nuestra [DOCUMENTACIÓN OFICIAL (DOCUMENTACION.md)](DOCUMENTACION.md).

---
*Que los Dioses de Bedrock tengan piedad de tu mundo.*
