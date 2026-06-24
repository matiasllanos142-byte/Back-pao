import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction

from api.models import Category, Product

User = get_user_model()

CATEGORIES = [
    {"slug": "estimulacion", "name": "Estimulación Cognitiva", "description": "Actividades para trabajar atención, memoria y funciones cognitivas.", "icon": "Brain", "color": "#7C3AED"},
    {"slug": "lectoescritura", "name": "Lectoescritura", "description": "Recursos para acompañar procesos de lectura y escritura.", "icon": "BookOpen", "color": "#F97316"},
    {"slug": "dislexia", "name": "Dislexia", "description": "Materiales de apoyo para dificultades relacionadas con lectura y escritura.", "icon": "BookMarked", "color": "#22C55E"},
    {"slug": "matematica", "name": "Matemática", "description": "Actividades de razonamiento lógico y habilidades matemáticas.", "icon": "Calculator", "color": "#06B6D4"},
    {"slug": "atencion-memoria", "name": "Atención y Memoria", "description": "Ejercicios de concentración, percepción y memoria.", "icon": "Eye", "color": "#EC4899"},
    {"slug": "funciones-ejecutivas", "name": "Funciones Ejecutivas", "description": "Actividades de planificación, organización y resolución de problemas.", "icon": "Puzzle", "color": "#FBBF24"},
]

PRODUCTS = [
    {
        "title": "Cuadernillo de Estimulación Cognitiva Inicial",
        "description": "Actividades graduadas para estimular la atención, la memoria de trabajo y el razonamiento lógico en niños de 5 a 8 años.",
        "price": "12.99",
        "category": "estimulacion",
        "image": "/images/products/cuadernillo-estimulacion-cognitiva.jpg",
        "badge": "Más vendido",
        "featured": True,
        "age": "5 - 8 años",
        "level": "Inicial",
        "features": ["30 actividades graduadas", "Instrucciones para el adulto", "Formato imprimible A4", "Clave de respuestas"],
        "objectives": ["Fortalecer la atención sostenida", "Desarrollar la memoria de trabajo", "Estimular el razonamiento lógico"],
    },
    {
        "title": "Actividades de Conciencia Fonológica",
        "description": "Serie de fichas para trabajar la conciencia fonológica: rimas, sílabas, sonidos iniciales y finales.",
        "price": "11.50",
        "category": "lectoescritura",
        "image": "/images/products/conciencia-fonologica.jpg",
        "badge": "Nuevo",
        "featured": True,
        "age": "4 - 7 años",
        "level": "Inicial",
        "features": ["25 fichas ilustradas", "Ejercicios progresivos", "Actividades orales y escritas", "Guía de uso para docentes"],
        "objectives": ["Desarrollar la conciencia fonológica", "Identificar rimas y sílabas", "Preparar la adquisición de la lectura"],
    },
    {
        "title": "Matemática Inicial",
        "description": "Cuadernillo con actividades de numeración, comparación de cantidades y primeras operaciones para Educación Infantil y 1.° de Primaria.",
        "price": "10.99",
        "category": "matematica",
        "image": "/images/products/matematica-inicial.jpg",
        "featured": True,
        "age": "5 - 7 años",
        "level": "Inicial",
        "features": ["20 actividades con dibujos", "Reconocimiento de números 1-20", "Comparación de cantidades", "Actividades manipulativas"],
        "objectives": ["Reconocer y escribir números", "Comparar cantidades", "Introducir el concepto de suma"],
    },
    {
        "title": "Atención Visual Nivel 1",
        "description": "Ejercicios de búsqueda visual, discriminación y seguimiento para mejorar la atención selectiva y sostenida.",
        "price": "9.99",
        "category": "atencion-memoria",
        "image": "/images/products/atencion-visual-n1.jpg",
        "badge": "Popular",
        "featured": True,
        "age": "6 - 10 años",
        "level": "Inicial",
        "features": ["15 ejercicios de búsqueda visual", "Actividades de discriminación", "Ejercicios de seguimiento", "Temporizador sugerido"],
        "objectives": ["Mejorar la atención selectiva", "Desarrollar la discriminación visual", "Fortalecer la atención sostenida"],
    },
    {
        "title": "Memoria y Secuencias",
        "description": "Actividades para trabajar la memoria visual y auditiva mediante secuencias de imágenes, números y palabras.",
        "price": "11.99",
        "category": "atencion-memoria",
        "image": "/images/products/memoria-secuencias.jpg",
        "featured": True,
        "age": "6 - 12 años",
        "level": "Intermedio",
        "features": ["20 actividades de secuencias", "Ejercicios de memoria visual", "Ejercicios de memoria auditiva", "Diferentes niveles de dificultad"],
        "objectives": ["Fortalecer la memoria de trabajo", "Desarrollar la secuenciación", "Mejorar la capacidad de retención"],
    },
    {
        "title": "Lectura Rápida y Comprensión",
        "description": "Fichas graduadas para mejorar la velocidad lectora y la comprensión textual en primaria y secundaria.",
        "price": "13.50",
        "category": "lectoescritura",
        "image": "/images/products/lectura-comprension.jpg",
        "featured": True,
        "age": "8 - 14 años",
        "level": "Intermedio",
        "features": ["30 fichas de comprensión", "Textos graduados por nivel", "Ejercicios de velocidad lectora", "Actividades de inferencia"],
        "objectives": ["Aumentar la velocidad lectora", "Mejorar la comprensión textual", "Desarrollar estrategias de lectura"],
    },
    {
        "title": "Apoyo en Dislexia - Nivel Inicial",
        "description": "Material estructurado con ejercicios multisensoriales para el refuerzo de la lectura y escritura en niños con dislexia.",
        "price": "14.99",
        "category": "dislexia",
        "image": "/images/products/apoyo-dislexia.jpg",
        "featured": False,
        "age": "6 - 10 años",
        "level": "Inicial",
        "features": ["25 ejercicios multisensoriales", "Enfoque kinestésico", "Actividades de conciencia fonológica", "Guía para padres y docentes"],
        "objectives": ["Reforzar la decodificación", "Mejorar la fluidez lectora", "Reducir la frustración en la lectura"],
    },
    {
        "title": "Planificación y Organización",
        "description": "Actividades para fortalecer funciones ejecutivas: planificación de tareas, establecimiento de prioridades y resolución de problemas.",
        "price": "12.50",
        "category": "funciones-ejecutivas",
        "image": "/images/products/planificacion-organizacion.jpg",
        "featured": False,
        "age": "8 - 14 años",
        "level": "Intermedio",
        "features": ["15 actividades prácticas", "Plantillas de planificación", "Escenarios de resolución de problemas", "Actividades de toma de decisiones"],
        "objectives": ["Desarrollar la planificación", "Fortalecer la organización", "Mejorar la resolución de problemas"],
    },
]


class Command(BaseCommand):
    help = "Seed initial data for Paola.Psicope"

    def handle(self, *args, **kwargs):
        with transaction.atomic():
            self.stdout.write("Creating categories...")
            for cat_data in CATEGORIES:
                Category.objects.update_or_create(slug=cat_data["slug"], defaults=cat_data)

            self.stdout.write("Creating products...")
            for prod_data in PRODUCTS:
                category = Category.objects.get(slug=prod_data.pop("category"))
                Product.objects.update_or_create(
                    title=prod_data["title"],
                    defaults={**prod_data, "category": category},
                )

            self.stdout.write("Creating admin user...")
            admin_email = os.environ.get("ADMIN_EMAIL", "admin@paolapsicope.com").lower()
            admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
            User.objects.filter(email=admin_email).delete()
            User.objects.create_superuser(
                username=admin_email,
                email=admin_email,
                first_name="Admin",
                password=admin_password,
                is_admin=True,
            )

        self.stdout.write(self.style.SUCCESS("Seed completed successfully."))
