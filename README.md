# Oráculo BDS Assistant

Oráculo BDS Assistant es un bot avanzado y sistema de asistencia impulsado por inteligencia artificial para Minecraft Bedrock Dedicated Server (BDS). Utiliza una arquitectura basada en Webhooks, RCON y Google Gemini Pro para crear una entidad interactiva (El Oráculo) capaz de entender a los jugadores, proponer acertijos, recibir sacrificios y controlar el mundo de Minecraft.

## Características Principales

- **Chatbot Inteligente (Google Gemini):** El Oráculo responde a los jugadores en el chat de Minecraft de forma inmersiva y mística, interpretando intenciones mediante IA.
- **Sistema de Devoción:** Los jugadores pueden interactuar, pedir favores y participar en pruebas para ganar el favor de los dioses.
- **Acertijos del Oráculo:** El Oráculo puede retar a los jugadores con acertijos. Si aciertan, el Oráculo limpia el clima u otorga recompensas. Si fallan, pueden ser castigados.
- **Sacrificios y Ofrendas:** Los jugadores pueden ofrecer objetos tirándolos frente al bloque del Oráculo. La IA evalúa el valor y rareza del objeto, y recompensa o castiga al jugador según su nivel de devoción.
- **Control del Mundo (RCON):** El Oráculo tiene poder sobre el clima, el tiempo (día/noche), puede dar objetos (`/give`) y lanzar rayos (`/summon lightning_bolt`), todo procesado a través de comprensión del lenguaje natural.

## Arquitectura del Proyecto

El proyecto está dividido en dos partes principales:

1. **Entorno Python (Raíz):**
   Contiene el servidor Flask (webhooks), el cliente RCON y la lógica principal de la IA.
   - `main.py`: Punto de entrada principal. Coordina webhooks, RCON y las interacciones del Oráculo.
   - `ai_handler.py`: Módulo para procesar los prompts de Gemini, categorizar intenciones (charlar, acertijo, clima, item) y evaluar la validez de los sacrificios.
   - `rcon_client.py`: Cliente asíncrono para enviar comandos directamente a la consola del servidor de Minecraft.
   - `devocion.json`: Archivo para almacenar el estado y nivel de "devoción" y variables (como estado de acertijos) de los jugadores.
   - `requirements.txt`: Dependencias de Python del proyecto.
   - `.env`: Variables de entorno (API keys, configuración de puertos).

2. **Behavior Pack (`oraculo_bridge/`):**
   Esta carpeta contiene el add-on (behavior pack) que debe ser instalado en el servidor de Minecraft Bedrock. 
   - `manifest.json`: Manifiesto del Behavior Pack. Requiere permisos para `@minecraft/server` y `@minecraft/server-net`.
   - `scripts/main.js`: Script en JavaScript que se ejecuta dentro del juego. Captura mensajes del chat, detecta objetos tirados (sacrificios) y se comunica con el servidor Python a través de HTTP.

## Requisitos previos

- Python 3.8 o superior.
- Servidor de Minecraft Bedrock Dedicated Server (BDS) con soporte para scripting (API de scripts habilitada).
- Acceso a RCON habilitado en el servidor (`server.properties`).
- Una API Key de **Google Gemini** (`GOOGLE_API_KEY`).

## Instalación y Configuración

1. **Instalar dependencias de Python:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Variables de Entorno:**
   Crea un archivo `.env` en la raíz del proyecto (este archivo es ignorado por git por seguridad). Agrega tus credenciales y configuración:
   ```env
   # API Keys
   GOOGLE_API_KEY=tu_api_key_de_gemini

   # Configuración de RCON
   RCON_HOST=127.0.0.1
   RCON_PORT=25575
   RCON_PASSWORD=tu_contraseña_rcon
   ```

3. **Instalación del Behavior Pack:**
   Copia el contenido de la carpeta `oraculo_bridge/` al directorio `behavior_packs` de tu servidor en la VPS y asegúrate de habilitarlo. Asegúrate de configurar la IP correcta hacia donde está corriendo el servidor Python dentro de `main.js`.

## Uso

Para iniciar el bot y el servidor de webhooks localmente:
```bash
python main.py
```
*(Nota: Asegúrate de tener los puertos de webhook abiertos (por defecto 5000) y el RCON correctamente configurado para que el script pueda interactuar con el servidor de Minecraft)*.
