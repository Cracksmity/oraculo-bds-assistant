# 👁️ Oráculo BDS Assistant

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Minecraft](https://img.shields.io/badge/Minecraft%20Bedrock-Dedicated%20Server-green)
![Gemini Pro](https://img.shields.io/badge/AI-Google%20Gemini%20Pro-orange)

**Oráculo BDS Assistant** es un sistema de asistencia avanzado y misterioso impulsado por inteligencia artificial para servidores de Minecraft Bedrock (BDS). Diseñado con una arquitectura híbrida (Webhooks + RCON + Google Gemini Pro), este bot introduce una deidad interactiva en tu mundo: **El Oráculo**.

El Oráculo es capaz de entender lenguaje natural, juzgar las acciones de los jugadores, proponer acertijos, exigir sacrificios y, en última instancia, manipular el mismísimo clima y la vida en el servidor.

---

## ✨ Características Principales

*   **🗣️ Interacción Divina (Gemini Pro):** Respuestas inmersivas y místicas en el chat del juego. El Oráculo comprende el contexto y las intenciones de los jugadores mediante procesamiento de lenguaje natural.
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
    *   `main.py`: El corazón del sistema. Coordina los endpoints de Webhook y los envíos por RCON.
    *   `ai_handler.py`: Interfaz con Gemini Pro. Clasifica intenciones (charlas, clima, sacrificios, biomas) y moldea la personalidad del Oráculo.
    *   `biome_finder.py`: Sistema automatizado para el cálculo de distancias a biomas basado en la semilla del mundo.
    *   `rcon_client.py`: Puente asíncrono para inyectar comandos directamente en la consola del BDS.
    *   `devocion.json`: Base de datos de jugadores que registra sus niveles de favor divino y progreso.

2.  **👁️ Los Ojos y Oídos (JavaScript - Behavior Pack):**
    Ubicado en `oraculo_bridge/`. Se ejecuta dentro del mundo de Minecraft.
    *   Captura eventos del chat (`beforeChatSend`).
    *   Detecta ítems arrojados en el mundo (sacrificios).
    *   Se comunica mediante peticiones HTTP (`@minecraft/server-net`) con el cerebro de Python.

---

## 🛠️ Requisitos e Instalación

### Requisitos Previos
*   Python 3.8 o superior.
*   Servidor Bedrock Dedicated Server (BDS) con **Beta APIs habilitadas** (o las APIs estables necesarias para script-net).
*   Acceso a RCON activado en `server.properties` (`enable-rcon=true`).
*   Una API Key válida de [Google AI Studio (Gemini)](https://aistudio.google.com/).

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
    GOOGLE_API_KEY=tu_api_key_aqui

    # Configuración del Servidor y Mundo
    WORLD_SEED=tu_semilla_del_mundo
    ADMIN_PLAYERS=tu_nombre_de_jugador
    DIVINE_FAVOR_PLAYERS=jugador_VIP1,jugador_VIP2

    # Configuración de RCON
    RCON_HOST=127.0.0.1
    RCON_PORT=25575
    RCON_PASSWORD=tu_password_fuerte
    ```
4.  **Instala el Behavior Pack:**
    *   Copia la carpeta `oraculo_bridge/` dentro de la carpeta `behavior_packs` de tu BDS.
    *   Aplica el pack al mundo y **activa las opciones de experimentación necesarias** (Beta APIs / Scripts).
    *   *Nota:* Asegúrate de que el archivo `scripts/main.js` del addon apunte a la IP y puerto correctos de tu servidor Python (por defecto `http://127.0.0.1:5000`).
5.  **Despierta al Oráculo:**
    ```bash
    python main.py
    ```

---

## 📚 Documentación y Secretos

Para más detalles sobre cómo personalizar al Oráculo, las reglas del sistema de Devoción y los **Misterios (Easter Eggs)** ocultos que puedes implementar en tu servidor, consulta nuestra [DOCUMENTACIÓN OFICIAL (DOCUMENTACION.md)](DOCUMENTACION.md).

---
*Que los Dioses de Bedrock tengan piedad de tu mundo.*
