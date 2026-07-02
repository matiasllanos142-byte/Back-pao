from django.utils import timezone
import re


ACTIVITY_LIBRARY = [
    {
        "type": "attention-search",
        "title": "Busca y marca",
        "skill": "atencion sostenida y rastreo visual",
        "objective": "Sostener la atencion mientras identifica estimulos objetivo.",
        "resource": "escena con objetos repetidos",
    },
    {
        "type": "working-memory",
        "title": "Recuerdo en orden",
        "skill": "memoria de trabajo",
        "objective": "Recordar y ordenar informacion visual breve.",
        "resource": "tarjetas secuenciales",
    },
    {
        "type": "planning",
        "title": "Planifico mi tarea",
        "skill": "planificacion y organizacion",
        "objective": "Anticipar pasos, materiales y tiempos de una actividad.",
        "resource": "agenda, checklist y utiles escolares",
    },
    {
        "type": "inhibition",
        "title": "Pienso antes de responder",
        "skill": "control inhibitorio",
        "objective": "Detener respuestas impulsivas y revisar consignas.",
        "resource": "semaforo de autocontrol",
    },
    {
        "type": "sequence",
        "title": "Ordeno la secuencia",
        "skill": "secuenciacion temporal",
        "objective": "Organizar acciones en un orden logico.",
        "resource": "viñetas de una rutina",
    },
    {
        "type": "classification",
        "title": "Agrupo por criterio",
        "skill": "flexibilidad cognitiva y categorizacion",
        "objective": "Clasificar elementos segun color, funcion o contexto.",
        "resource": "objetos tematicos recortables",
    },
    {
        "type": "visual-discrimination",
        "title": "Iguales o diferentes",
        "skill": "percepcion visual",
        "objective": "Comparar detalles y discriminar diferencias relevantes.",
        "resource": "pares de escenas controladas",
    },
    {
        "type": "self-monitoring",
        "title": "Como me fue",
        "skill": "autorregulacion y metacognicion",
        "objective": "Registrar desempeno, esfuerzo y estrategia utilizada.",
        "resource": "escala simple de autoevaluacion",
    },
]


def _clean(value, fallback=""):
    text = str(value or "").strip()
    return text or fallback


def _int_between(value, minimum, maximum, fallback):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def _profile_for_pages(pages):
    if pages >= 100:
        return "programa largo tipo biblioteca profesional"
    if pages >= 70:
        return "guia extensa con teoria, practica y seguimiento"
    if pages >= 40:
        return "cuadernillo medio con evaluacion y entrenamiento"
    return "pack corto de actividades imprimibles"


def _theory_pages_for(pages):
    if pages >= 100:
        return 12
    if pages >= 70:
        return 8
    if pages >= 40:
        return 4
    return 2


def _activity_title(base, topic, index):
    topic_suffix = f" de {topic}" if topic else ""
    if index == 1:
        return f"{base}{topic_suffix}"
    return base


def infer_workbook_payload_from_chat(messages, skill_text=""):
    content = "\n".join(
        str(message.get("content", ""))
        for message in messages
        if isinstance(message, dict)
    ).strip()
    normalized = content.lower()

    pages = 20
    page_match = re.search(r"(\d{1,3})\s*(?:paginas|p[aá]ginas|hojas|actividades)", normalized)
    if page_match:
        pages = int(page_match.group(1))

    age = ""
    age_match = re.search(r"(\d{1,2})\s*(?:anos|a[nñ]os)", normalized)
    if age_match:
        age = f"{age_match.group(1)} anos"

    difficulty = "Media"
    if re.search(r"\b(facil|f[aá]cil|baja|simple)\b", normalized):
        difficulty = "Facil"
    elif re.search(r"\b(dificil|dif[ií]cil|alta|avanzada)\b", normalized):
        difficulty = "Alta"

    topic_keywords = [
        ("tdah", "TDAH"),
        ("tea", "TEA"),
        ("autismo", "TEA / Autismo"),
        ("discalculia", "Discalculia"),
        ("dislexia", "Dislexia"),
        ("lectoescritura", "Lectoescritura"),
        ("futbol", "Funciones ejecutivas con tematica futbol"),
        ("fútbol", "Funciones ejecutivas con tematica futbol"),
        ("memoria", "Atencion y memoria"),
        ("atencion", "Atencion y memoria"),
        ("atención", "Atencion y memoria"),
        ("funciones ejecutivas", "Funciones ejecutivas"),
        ("habitos", "Habitos de estudio"),
        ("hábitos", "Habitos de estudio"),
        ("emociones", "Autorregulacion emocional"),
    ]
    topic = ""
    for needle, value in topic_keywords:
        if needle in normalized:
            topic = value
            break

    if not topic:
        compact = re.sub(r"\s+", " ", content)
        topic = compact[:90] or "habilidades de aprendizaje"

    title = f"Cuadernillo psicopedagogico de {topic}"
    if age:
        title = f"{title} - {age}"

    style = "Canva educativo profesional, A4 vertical, colores claros, actividades imprimibles"
    if "princesa" in normalized or "princesas" in normalized:
        style = "Canva educativo con tematica de princesas, colores pastel, A4 vertical"
    elif "futbol" in normalized or "fútbol" in normalized:
        style = "Canva educativo deportivo, futbol infantil, colores vivos, A4 vertical"

    return {
        "title": title,
        "brief": content,
        "topic": topic,
        "age": age or "edad a definir",
        "difficulty": difficulty,
        "pages": pages,
        "style": style,
        "skill": skill_text,
    }


def build_workbook_plan(payload):
    topic = _clean(payload.get("topic"), _clean(payload.get("brief"), "habilidades de aprendizaje"))
    age = _clean(payload.get("age"), "edad a definir")
    difficulty = _clean(payload.get("difficulty"), "media")
    style = _clean(payload.get("style"), "Canva educativo, colores claros, A4 vertical")
    pages = _int_between(payload.get("pages"), 8, 140, 20)
    title = _clean(payload.get("title"), f"Cuadernillo psicopedagogico de {topic}")
    brief = _clean(payload.get("brief"), f"{topic}, {age}, dificultad {difficulty}")

    closing_pages = 3 if pages >= 20 else 2 if pages >= 12 else 1
    fixed_pages = 1 + 1 + closing_pages
    theory_pages = min(_theory_pages_for(pages), max(1, pages - fixed_pages - 4))
    activity_count = max(1, pages - fixed_pages - theory_pages)

    activities = []
    for index in range(1, activity_count + 1):
        template = ACTIVITY_LIBRARY[(index - 1) % len(ACTIVITY_LIBRARY)]
        activities.append(
            {
                "number": index,
                "title": _activity_title(template["title"], topic, index),
                "type": template["type"],
                "skill": template["skill"],
                "objective": template["objective"],
                "difficulty": difficulty,
                "visualResource": template["resource"],
                "instruction": "Lee la consigna, completa la actividad y revisa tu respuesta antes de avanzar.",
                "answerKeyReady": True,
            }
        )

    image_prompts = [
        {
            "key": "cover",
            "usage": "Portada",
            "prompt": (
                f"Friendly educational cover illustration for a Spanish printable workbook about {topic}, "
                f"for {age}, bright clean Canva style, no text, no letters, no watermark"
            ),
        },
        {
            "key": "intro",
            "usage": "Introduccion",
            "prompt": (
                f"Warm classroom scene with organized school supplies and children working calmly on {topic}, "
                "pastel colors, no text, no letters, no watermark"
            ),
        },
    ]

    for activity in activities[: min(len(activities), 24)]:
        image_prompts.append(
            {
                "key": f"activity-{activity['number']}",
                "usage": activity["title"],
                "prompt": (
                    f"Child-friendly educational illustration for {activity['visualResource']} related to {topic}, "
                    f"{style}, no text, no letters, no watermark"
                ),
            }
        )

    structure = [
        {"section": "Portada", "pages": 1},
        {"section": "Como usar este cuadernillo e indice visual", "pages": 1},
        {"section": "Marco psicopedagogico y objetivos", "pages": theory_pages},
        {"section": "Actividades practicas", "pages": activity_count},
    ]
    if closing_pages >= 1:
        structure.append({"section": "Registro de avances", "pages": 1})
    if closing_pages >= 2:
        structure.append({"section": "Diploma o certificado", "pages": 1})
    if closing_pages >= 3:
        structure.append({"section": "Cierre para familia/profesional", "pages": 1})

    return {
        "title": title,
        "brief": brief,
        "topic": topic,
        "age": age,
        "difficulty": difficulty,
        "totalPages": sum(item["pages"] for item in structure),
        "requestedPages": pages,
        "profile": _profile_for_pages(pages),
        "style": style,
        "skill": _clean(payload.get("skill"), ""),
        "structure": structure,
        "activities": activities,
        "imagePrompts": image_prompts,
        "productionNotes": [
            "Las actividades se resuelven con plantillas verificables; la imagen IA queda como recurso visual.",
            "Las ilustraciones no deben incluir texto para evitar errores de lectura.",
            "El PDF final debe salir en A4 vertical con margenes amplios para imprimir.",
        ],
        "generatedAt": timezone.now().isoformat(),
    }
