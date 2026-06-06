import logging
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

class AIHandler:
    """
    Clase que interactúa con la API de OpenAI para generar respuestas narrativas,
    místicas y poéticas (al estilo de un oráculo) en español.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        """
        Inicializa el cliente oficial de OpenAI.

        Args:
            api_key: La clave de la API de OpenAI.
            model: El modelo de lenguaje a utilizar (por defecto gpt-4o-mini).
        """
        self.client: OpenAI = OpenAI(api_key=api_key)
        self.model: str = model

    def generate_response(
        self,
        player_name: str,
        structure: str,
        x: Optional[str] = None,
        y: Optional[str] = None,
        z: Optional[str] = None,
        distance: Optional[float] = None,
        direction: Optional[str] = None,
        reveal_exact_coords: bool = False,
        devocion_rango: str = "Creyente"
    ) -> str:
        """
        Genera una respuesta del Oráculo en español para un jugador.
        Si reveal_exact_coords es True y se proveen coordenadas, las revela directamente en un texto poético.
        Si reveal_exact_coords es False y se proveen distancia y rumbo, genera una pista mística
        orientando al jugador (Norte, Suroeste, etc.) y la distancia aproximada sin revelar coordenadas.
        Si no hay datos de localización, responde líricamente que la estructura está oculta.

        Args:
            player_name: Nombre del jugador que hizo la pregunta.
            structure: Nombre de la estructura que se busca.
            x: Coordenada X (opcional).
            y: Coordenada Y (opcional).
            z: Coordenada Z (opcional).
            distance: Distancia en bloques al objetivo (opcional).
            direction: Rumbo cardinal al objetivo (opcional).
            reveal_exact_coords: Si es True, muestra las coordenadas exactas. Si es False, da pistas.

        Returns:
            str: Mensaje de respuesta místico (máximo 2 oraciones) en español.
        """
        has_coords = x is not None and z is not None
        has_hints = distance is not None and direction is not None

        # Definir los prompts del sistema y usuario según el modo de revelación
        if reveal_exact_coords and has_coords:
            system_prompt = (
                "Eres el Oráculo de un servidor de Minecraft Bedrock. Eres un ser ancestral, sabio, místico y enigmático. "
                "Hablas siempre en español, con un tono poético, misterioso y sagrado. "
                "Tus respuestas deben ser muy cortas y concisas: máximo 2 oraciones. "
                "Debes integrar las coordenadas provistas en tu profecía de forma natural y legible para el jugador."
            )
            user_prompt = (
                f"El mortal '{player_name}' busca la ubicación de la estructura '{structure}'. "
                f"Los astros revelan que se encuentra en las coordenadas X: {x}, Y: {y if y else '~'}, Z: {z}. "
                "Genera tu revelación mística incluyendo estas coordenadas en español (máximo 2 oraciones)."
            )
        elif not reveal_exact_coords and has_hints:
            system_prompt = (
                "Eres el Oráculo de un servidor de Minecraft Bedrock. Eres un ser ancestral, sabio, místico y enigmático. "
                "Hablas siempre en español, con un tono poético, misterioso y sagrado. "
                "Tus respuestas deben ser muy cortas y concisas: máximo 2 oraciones. "
                "DEBES guiar al jugador dándole la dirección cardinal (ej. Norte, Suroeste) y la distancia aproximada en bloques "
                "que se te proporciona. "
                "CRÍTICO: No reveles bajo ninguna circunstancia coordenadas exactas X, Y o Z en números. "
                "Tus profecías deben guiar al jugador mediante el rumbo y la distancia cósmica."
            )
            user_prompt = (
                f"El mortal '{player_name}' busca la ubicación de la estructura '{structure}'. "
                f"Los astros indican que está a una distancia aproximada de {distance:.0f} bloques hacia el {direction}. "
                "Guíalo en español de forma mística usando estos datos, sin mencionar coordenadas X, Y, Z (máximo 2 oraciones)."
            )
        else:
            # Caso en el que no se encontró la estructura
            system_prompt = (
                "Eres el Oráculo de un servidor de Minecraft Bedrock. Eres un ser ancestral, sabio, místico y enigmático. "
                "Hablas siempre en español, con un tono poético, misterioso y sagrado. "
                "Tus respuestas deben ser muy cortas y concisas: máximo 2 oraciones. "
                "Explica místicamente que tus visiones no alcanzan a percibir la estructura solicitada, o que esta se oculta en las sombras."
            )
            user_prompt = (
                f"El mortal '{player_name}' busca la estructura '{structure}', pero la magia de localización ha fallado. "
                "Explica místicamente que este lugar está oculto de tu visión en un máximo de 2 oraciones en español."
            )

        # Modificador de tono según la devoción del jugador
        tone_modifier = ""
        if devocion_rango == "Predilecto":
            tone_modifier = " Este jugador es tu predilecto, un ser de altísima devoción. Háblale con gracia divina, aprecio y entusiasmo sagrado."
        elif devocion_rango in ("Hereje", "Indigno"):
            tone_modifier = " Este jugador es un hereje o indigno. Sé extremadamente frío, hostil, severo y amenazante en tu profecía."
        system_prompt += tone_modifier

        try:
            logger.info(f"Enviando solicitud a OpenAI ({self.model}) para {player_name}. Coords exactas: {reveal_exact_coords}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=150,
                temperature=0.7
            )
            
            ai_message = response.choices[0].message.content
            if ai_message:
                result = ai_message.strip()
                logger.info(f"Respuesta generada con éxito: {result}")
                return result
            else:
                raise ValueError("La respuesta de OpenAI retornó vacía.")

        except Exception as e:
            logger.error(f"Error al llamar a la API de OpenAI: {e}", exc_info=True)
            return "Los astros están nublados y la visión del Oráculo se ha oscurecido... Inténtalo más tarde."

    def generate_item_response(
        self,
        player_name: str,
        item: str,
        outcome: str,  # "success", "fail", "punished", "smited", "insult_smited"
        effect: Optional[str] = None,
        devocion_rango: str = "Creyente"
    ) -> str:
        """
        Genera respuestas místicas en español para la petición de ítems y sus consecuencias.
        Soporta resultados de Éxito, Fallo, Castigo, Smite (Rayo) e Ira por Insulto.
        """
        if outcome == "success":
            system_prompt = (
                "Eres el Oráculo de un servidor de Minecraft Bedrock. Hablas en español, con un tono místico, sabio y poético. "
                "Tus respuestas deben ser de máximo 2 oraciones. Un jugador ha pedido un obsequio y los dioses han decidido concedérselo. "
                "Dile de forma solemne y misteriosa que su deseo ha sido materializado en su inventario."
            )
            user_prompt = (
                f"El mortal '{player_name}' ha pedido '{item}' y la fortuna divina le sonrió. "
                "Anuncia con enigma que le has concedido el ítem (máximo 2 oraciones)."
            )
        elif outcome == "fail":
            system_prompt = (
                "Eres el Oráculo de un servidor de Minecraft Bedrock. Hablas en español, con un tono místico, sabio y poético. "
                "Tus respuestas deben ser de máximo 2 oraciones. Un jugador ha pedido un obsequio pero los astros no le favorecen. "
                "Dile con sabiduría y enigma que los dioses no complacen caprichos egoístas hoy y que debe ser paciente."
            )
            user_prompt = (
                f"El mortal '{player_name}' pidió '{item}' pero la fortuna no le favorece. "
                "Niégale el ítem con palabras misteriosas sin sonar agresivo, sino sabio (máximo 2 oraciones)."
            )
        elif outcome == "punished":
            system_prompt = (
                "Eres el Oráculo de un servidor de Minecraft Bedrock. Hablas en español, con un tono solemne, poético y amenazador. "
                "Tus respuestas deben ser de máximo 2 oraciones. Un jugador codicioso ha solicitado demasiados obsequios y ha fallado, "
                "por lo que los astros le han impuesto un castigo corporal/efecto adverso de estado. "
                f"Dile con severidad que su insistencia egoísta ha despertado el malestar del Oráculo y describe místicamente el castigo: '{effect}'."
            )
            user_prompt = (
                f"El mortal '{player_name}' ha pecado de codicia al insistir en pedir '{item}' y ha sido castigado con '{effect}'. "
                "Redacta su severa advertencia y describe místicamente su castigo de estado (máximo 2 oraciones)."
            )
        elif outcome == "smited":
            system_prompt = (
                "Eres el Oráculo de un servidor de Minecraft Bedrock. Hablas en español, con un tono severo, atronador y poético. "
                "Tus respuestas deben ser de máximo 2 oraciones. Un jugador ha ignorado múltiples castigos de codicia. "
                "Los dioses lo han fulminado directamente con un rayo divino (smite) quitándole la vida. "
                "Dile con tono apocalíptico que su alma ha sido reducida a cenizas por tentar al destino."
            )
            user_prompt = (
                f"El mortal '{player_name}' ha ignorado 3 castigos consecutivos. El rayo divino (smite) lo ha desintegrado. "
                "Redacta su trágica y solemne condena por desafiar la paciencia cósmica (máximo 2 oraciones)."
            )
        elif outcome == "insult_smited":
            system_prompt = (
                "Eres el Oráculo de un servidor de Minecraft Bedrock. Hablas en español, con un tono sumamente iracundo, majestuoso, severo y poético. "
                "Tus respuestas deben ser de máximo 2 oraciones. Un mortal insolente e insensato ha osado insultar al Oráculo. "
                "La ira del Oráculo lo ha fulminado instantáneamente con un rayo divino (smite) reduciéndolo a cenizas en el acto. "
                "Dile de forma aterradora que la blasfemia contra el Oráculo se paga con la vida eterna."
            )
            user_prompt = (
                f"El mortal '{player_name}' insultó al Oráculo y fue fulminado inmediatamente por un rayo. "
                "Declara la sentencia fulminante y advierte a otros sobre la insolencia (máximo 2 oraciones)."
            )
        else:
            return "Los astros guardan silencio."

        # Modificador de tono según la devoción del jugador (solo si no es fulminado directamente)
        if outcome not in ("smited", "insult_smited"):
            tone_modifier = ""
            if devocion_rango == "Predilecto":
                tone_modifier = " Este jugador es tu predilecto, un ser de altísima devoción. Háblale con gracia divina, aprecio y entusiasmo sagrado."
            elif devocion_rango in ("Hereje", "Indigno"):
                tone_modifier = " Este jugador es un hereje o indigno. Sé extremadamente frío, hostil, severo y amenazante."
            system_prompt += tone_modifier

        try:
            logger.info(f"Enviando solicitud de ítem/castigo a OpenAI ({self.model}) para {player_name} - Resultado: {outcome}...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=150,
                temperature=0.8
            )
            ai_message = response.choices[0].message.content
            if ai_message:
                return ai_message.strip()
            else:
                raise ValueError("La respuesta de OpenAI retornó vacía.")
        except Exception as e:
            logger.error(f"Error al llamar a la API de OpenAI para ítem: {e}", exc_info=True)
            if outcome == "success":
                return f"Los dioses son generosos, {player_name}. Disfruta de tu {item}."
            elif outcome in ("punished", "smited", "insult_smited"):
                return f"La ira cósmica ha caído sobre ti, {player_name}."
            else:
                return "Los astros están nublados, intenta más tarde."

    def generate_riddle(self) -> dict:
        """
        Genera un acertijo místico sobre Minecraft Bedrock y su respuesta de una palabra.
        Retorna un diccionario: {"riddle": str, "answer": str}
        """
        system_prompt = (
            "Eres el Oráculo de un servidor de Minecraft Bedrock. Hablas siempre en español, con un tono poético, misterioso y sagrado. "
            "Debes crear un acertijo enigmático y divertido sobre Minecraft Bedrock (puede ser sobre un bloque, un mob, un ítem o una mecánica). "
            "El acertijo debe ser corto (máximo 2 oraciones). "
            "Debes responder ÚNICAMENTE con un objeto JSON válido que contenga las llaves 'riddle' (el acertijo en español) "
            "y 'answer' (la respuesta al acertijo en una sola palabra, en minúsculas, sin espacios y sin acentos gráficos/tildes)."
        )
        user_prompt = "Genera un nuevo acertijo de Minecraft ahora."

        try:
            logger.info("Enviando solicitud a OpenAI para generar acertijo...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=150,
                temperature=0.8
            )
            
            ai_message = response.choices[0].message.content
            if ai_message:
                import json
                data = json.loads(ai_message.strip())
                logger.info(f"Acertijo generado con éxito: {data}")
                return {
                    "riddle": data.get("riddle", "Tengo ojos pero no veo, viajo por portales y floto en el vacío. ¿Qué soy?"),
                    "answer": data.get("answer", "enderdragon").lower().strip()
                }
            else:
                raise ValueError("La respuesta de OpenAI retornó vacía.")

        except Exception as e:
            logger.error(f"Error al generar el acertijo con OpenAI: {e}", exc_info=True)
            # Acertijo de respaldo por si falla la API
            return {
                "riddle": "Brillo bajo tierra en lo profundo, pero si me tocas con piedra te deshaces de mi don. ¿Qué mineral soy?",
                "answer": "hierro"
            }

