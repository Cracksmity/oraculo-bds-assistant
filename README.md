# Oráculo BDS Assistant

Oráculo BDS Assistant es un bot avanzado y sistema de asistencia para Minecraft Bedrock Dedicated Server (BDS). Utiliza una arquitectura basada en Webhooks y RCON para conectar el servidor de Minecraft con scripts de Python, permitiendo la administración, análisis y monitoreo en tiempo real.

## Arquitectura del Proyecto

El proyecto está dividido en dos partes principales:

1. **Entorno Python (Raíz):**
   Contiene el servidor de webhooks, el cliente RCON, el monitoreo de logs y la lógica principal del bot (IA). 
   - `main.py`: Punto de entrada principal.
   - `webhook_server.py`: Servidor que escucha los eventos enviados desde el servidor de Minecraft.
   - `rcon_client.py`: Cliente para enviar comandos directamente a la consola del servidor.
   - `ai_handler.py`: Módulo para procesar y manejar la inteligencia artificial y la toma de decisiones.
   - `log_monitor.py`: Sistema de monitoreo de registros (logs) del servidor en tiempo real.
   - `devocion.json`: Archivo para el estado y configuración de "devoción".
   - `requirements.txt`: Dependencias de Python del proyecto.

2. **Behavior Pack (`oraculo_bridge/`):**
   Esta carpeta contiene el add-on (behavior pack) que debe ser instalado en el servidor de Minecraft Bedrock. Está diseñado de forma modular para que sea fácil identificar exactamente qué archivos subir a la VPS por SFTP sin mezclarlos con el entorno de Python.
   - `manifest.json`: Manifiesto del Behavior Pack.
   - `scripts/`: Carpeta con los scripts en JavaScript que se ejecutan dentro del juego y se comunican con el servidor de webhooks de Python.

## Requisitos previos

- Python 3.8 o superior.
- Servidor de Minecraft Bedrock Dedicated Server (BDS) con soporte para scripting (GameTest Framework / `@minecraft/server`).
- Acceso a RCON habilitado en el servidor (`server.properties`).

## Instalación y Configuración

1. **Instalar dependencias de Python:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Variables de Entorno:**
   Crea un archivo `.env` en la raíz del proyecto (este archivo es ignorado por git por seguridad). Agrega tus credenciales y configuración (por ejemplo, puerto RCON, contraseña RCON, URL del webhook, etc.). No subas este archivo a repositorios públicos.

3. **Instalación del Behavior Pack:**
   Copia el contenido de la carpeta `oraculo_bridge/` al directorio `behavior_packs` (o directamente al folder del mundo) de tu servidor en la VPS y asegúrate de habilitarlo.

## Uso

Para iniciar el bot y el servidor de webhooks localmente:
```bash
python main.py
```
*(Nota: Asegúrate de tener los puertos de webhook abiertos y el RCON correctamente configurado para que el script pueda interactuar con el servidor de Minecraft)*.
