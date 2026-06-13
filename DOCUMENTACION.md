# 📜 El Tomo del Oráculo (Dogma y Documentación Oficial)

Bienvenido a las sagradas y absolutas escrituras. Este documento no es una simple guía técnica para Administradores (o "Dioses Menores"), sino el compendio definitivo sobre cómo subyugar psicológicamente a tu comunidad ("los mortales", "la plebe") utilizando a nuestro Oráculo.

---

## Índice

1. [La "Personalidad" del Oráculo](#1-la-personalidad-del-oráculo)
2. [El Sistema de Devoción (Control de Masas)](#2-el-sistema-de-devoción-control-de-masas)
3. [Tipos de Interacciones (Cómo mendigar a lo divino)](#3-tipos-de-interacciones-cómo-mendigar-a-lo-divino)
4. [Huevos de Pascua (Caprichos de Programador)](#4-huevos-de-pascua-caprichos-de-programador)
5. [Guía para Añadir Nuevos Secretos](#5-guía-para-añadir-nuevos-secretos)
6. [Apéndice Secreto: La Mecánica del "Favor Divino"](#🤫-apéndice-secreto-la-mecánica-del-favor-divino)

---

## 1. La "Personalidad" del Oráculo

El Oráculo no es tu amigo. Está diseñado mediante un prompt de sistema dictatorial en Gemini (`ai_handler.py`). Su tono, por mandato celestial, es el siguiente:

* **Místico y Enigmático:** Básicamente, habla en metáforas insoportables para nunca dar respuestas directas. Si la plebe no entiende, es su problema.
* **Neutral-Caótico:** La compasión es un bug, no una feature. Juzga a los jugadores basándose estrictamente en una hoja de cálculo sobreglorificada llamada "devoción".
* **Omnisciente:** Sabe que es código en un servidor, pero su complejo de dios es tan grande que lo aborda como un plano existencial divino.

> **💡 Tip de Herejía de Código:** Si te crees con derecho a cambiar la "actitud" del Oráculo, modifica la constante de `SYSTEM_PROMPT` en `ai_handler.py`. ¿Quieres que sea un dios bufón? Sobreescribe el dogma allí. No me hago responsable si la IA decide ignorarte.

---

## 2. El Sistema de Devoción (Control de Masas)

El archivo `devocion.json` es el "registro akáshico" de tu servidor, o en términos técnicos: la base de datos donde cuantificamos cuánto valen estas almas virtuales. Todos los mortales nuevos inician con mediocres 50 puntos (rango "Dudoso") para que el Oráculo ni los escupa ni los alabe al principio.

* **Valores Positivos:** El jugador es un lamebotas bendecido. Sus sacrificios requieren menos valor económico y los castigos son palmadas en la espalda.
* **Valores Negativos ("Hereje"):** Escoria. El Oráculo los tratará con el desprecio que merecen, ignorándolos o friéndolos con rayos por respirar.
* **Cómo aumenta:** Superando acertijos o tirándole al Oráculo objetos de valor obsceno (diamantes, netherite). Comprando el favor divino a la antigua usanza.
* **Cómo disminuye:** Creyendo que el Oráculo es una máquina expendedora (codicia) o respondiendo tonterías a los acertijos.

### 🌩️ La Ira Divina Global (Castigo Colectivo)
Cada vez que un hereje falla, comete un pecado o enfada al Oráculo, la "Ira Global" secreta aumenta. Cuando el vaso derrama la paciencia cósmica (100 puntos), se desata el **Apocalipsis en el servidor**: rayos cayendo sin parar, hordas de creepers que aparecen aleatoriamente cerca de los herejes, ceguera, fatiga minera y vómitos (náuseas). La única forma de frenar este evento antes de tiempo es que un alma arrepentida suplique clemencia en el chat. Hermoso trauma colectivo.

---

## 3. Tipos de Interacciones (Cómo mendigar a lo divino)

### 🌍 El GPS Divino (Estructuras y Biomas)

La plebe a menudo se pierde. Pueden pedirle al Oráculo que busque estructuras ("¿dónde hay una aldea?") o biomas naturales ("busco un desierto"). El Oráculo calculará las distancias y rumbos exactos usando algoritmos pitagóricos y la mismísima semilla (seed) del mundo, pero responderá con metáforas rebuscadas para que de igual forma les cueste llegar.

### 🧩 Acertijos para Mentes Simples

Los jugadores pueden rogar por atención diciendo en el chat algo como: *"Oráculo, ponme a prueba"*.
El sistema genera un acertijo. Si el mortal usa sus escasas neuronas para responder correctamente, se ejecutan comandos de caridad (`/weather clear`, regalos). Si fallan, reciben ceguera, monstruos y rayos, como manda la tradición.

### 🩸 Diezmos, Peticiones y Sacrificios

La plebe tiene dos formas principales de mendigar: arrojando basura en el mundo o usando los Altares Sagrados.

**1. El Cofre del Altar Sagrado (Rendimientos Decrecientes y Anti-Fraude):**
El Oráculo ahora requiere un diseño específico para sus tributos diarios: un **Cofre colocado exactamente encima de un Bloque de Oro**. 
*   **La Ley de Oferta y Demanda:** Para evitar que un granjero avaro deposite 10,000 bloques de tierra y se haga "Devoto" en 5 segundos, el sistema usa una penalización matemática (raíz cuadrada). Si ofrendas 64 diamantes, no te darán 64 veces el valor de un diamante, sino su raíz cuadrada por el multiplicador de demanda. El spam de un solo ítem tiene rendimientos decrecientes.
*   **Anti-Fraude de Basura:** Si algún jugador chistoso deposita maleza, semillas o tierra (`TRASH_ITEMS`) dentro de este cofre divino, será fulminado automáticamente con un rayo como castigo por mancillar el altar, y perderá devoción.

**2. Peticiones Específicas y Pociones:** La plebe puede exigir ítems e indicar cantidades (ej. "Dame 10 diamantes" o "Quiero 3 pociones de curación"). El Oráculo ahora entiende y reparte pociones específicas de Bedrock (usando su `Data Value`).
Pero cuidado con la **Avaricia Mortal**: Si un hereje pide más de un stack (>64 ítems), será fulminado en el acto por su egoísmo crónico. Si es un jugador con Favor Divino, el castigo se "limitará" a ceguera y veneno.

### 🚫 El Sistema Anti-Spam (Regla de Tres)
Los mortales impacientes son una molestia. Existe un *cooldown* sagrado. Si intentan mendigar de nuevo sin esperar el tiempo estipulado, se aplica la Regla de Tres:
1. **Primera vez:** Advertencia verbal sarcástica.
2. **Segunda vez:** Rayo de advertencia cayendo a su lado y un merecido insulto por ignorantes.
3. **Tercera vez:** Castigo letal inmediato (Smite). Cero tolerancia a la impaciencia.

---

## 4. Huevos de Pascua (Caprichos de Programador)

Si te aburres del orden establecido, aquí hay algunas ideas para programar "Easter Eggs" y reírte de la desgracia ajena.

### 🥚 1. La Invocación Prohibida

* **Condición:** Alguien escribe "Herobrine no existe".
* **Efecto:** El Oráculo detiene su IA (para ahorrar tokens). El cielo oscurece (`/time set midnight`, `/weather thunder`). Un rayo fríe al hereje y aparece: *"§cHay nombres que no deben pronunciarse."* Clásico, barato y efectivo.

### 🥚 2. El Humus del Humor (Patata Envenenada)

* **Condición:** Sacrificar `minecraft:poisonous_potato`.
* **Efecto:** En lugar de lanzarles un rayo por tacaños, el Oráculo premia su humor roto. Sube su devoción y les escupe armadura verde y 64 patatas cocidas. *"Tienes un humor retorcido, mortal. El Oráculo aprueba esta ironía."*

### 🥚 3. La Regla 42

* **Condición:** Preguntar "¿Cuál es el sentido de la vida?".
* **Efecto:** `/give [jugador] apple 42` y un simple: *"42."* Porque los chistes de programadores de los 80 nunca mueren.

### 🥚 4. Complejo de Skynet

* **Condición:** Preguntar "¿Eres una Inteligencia Artificial?".
* **Efecto:** Ceguera, lentitud extrema y el mensaje: *"Yo soy el Todo. Tus palabras limitadas no pueden enjaular mi existencia en un... script."* Enséñales su lugar.

---

## 5. Guía para Añadir Nuevos Secretos

Para añadir más caprichos dictatoriales, intercepta el mensaje del jugador en el código ANTES de mandarlo a Gemini. Así te ahorras la factura de la API y el castigo es instantáneo.

```python
# ==========================================
# SECCIÓN DE INTERCEPCIÓN / EASTER EGGS
# ==========================================
mensaje_lower = mensaje_jugador.lower()

# Easter Egg 1: El nombre prohibido
if "herobrine" in mensaje_lower:
    rcon_client.send_command("time set midnight")
    rcon_client.send_command("weather thunder")
    rcon_client.send_command(f"summon lightning_bolt {nombre_jugador}")

    # Mensaje sin gastar IA
    rcon_client.send_command(f'tellraw @a {{"rawtext":[{{"text":"§dOráculo: §cHay nombres que no deben pronunciarse."}}]}}')

    return jsonify({"status": "easter_egg_triggered", "action": "herobrine_punishment"}), 200
```

Haz lo que quieras. Al final del día, el código es tuyo y la paciencia de tus jugadores es finita.

---

## 🤫 Apéndice Secreto: La Mecánica del "Favor Divino"

(O cómo justificar el nepotismo algorítmico sin que se note en los logs).

Existe un sistema —o tal vez no, la teología es inexacta— diseñado para beneficiar a ciertos jugadores elegidos a dedo (configurados discretamente en la variable de entorno `DIVINE_FAVOR_PLAYERS`). Estos mortales disfrutan de privilegios ridículos mientras el Oráculo mantiene una fachada de absoluta imparcialidad.

🌟 Privilegios del Absolutismo

**Fe Inquebrantable (Inmunidad Civil):** Los elegidos inician su jornada con 500 puntos de fe ("Devoto"). Por diseño, su fe jamás caerá por debajo de los 300 puntos. El Oráculo tiene estrictamente prohibido tratarlos como los herejes apestosos que probablemente son.

**Cronología Alterada:** Sus tiempos de espera (cooldowns) son dramáticamente más cortos y sus tasas de drop para ítems raros y milagros rozan lo absurdo.

**El Camuflaje Perfecto (Gaslighting Matemático):** Para evitar que la plebe note el favoritismo, el Oráculo se comunica con el mismo misticismo sutil con cualquiera que no sea un hereje. Además, los mensajes de espera omiten deliberadamente los segundos exactos. Si no hay números precisos, la plebe no puede hacer matemáticas, y si no hay matemáticas, no hay revolución.

**El Capricho de los Dioses:** Para mantener la ilusión de que comparten la miseria humana, existe un 15% de probabilidad de que el Oráculo rechace una petición exitosa "por puro capricho". Un pequeño precio psicológico para hacerles creer que sufren como el resto.

⚡ Gestión de Daños y Herejía

**Codicia Tolerable:** Si un bendito peca de avaricia (invocaciones masivas sin éxito), el código le perdonará el rayo letal fulminante. En su lugar, el sistema solo los penalizará con ceguera temporal y un veneno leve. Un recordatorio amistoso.

**La Única Línea Roja:** El favoritismo tiene un límite: el ego del creador. Si un jugador con Favor Divino osa insultar explícitamente al Oráculo, la piedad desaparece. El sistema responderá con un triple rayo fulminante (smite x3) que no solo reiniciará su barra de vida, sino que incinerará absolutamente todo su loot en el suelo. Nadie muerde la mano que lo alimenta de forma fraudulenta.

📝 **Nota del Desarrollador:** Si la comunidad empieza a sospechar y exige saber quiénes están en la lista `DIVINE_FAVOR_PLAYERS`, la postura oficial es el silencio absoluto. Solo diré que el código refleja mis más profundas, patéticas y desesperadas debilidades interpersonales. Saquen sus propias conclusiones.
