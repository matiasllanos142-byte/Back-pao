# GitHub Releases — aplicación Android

El backend consulta la última Release estable del repositorio configurado y expone metadata segura y descarga por streaming. El cliente nunca recibe `browser_download_url`, la URL API del asset ni `GITHUB_TOKEN`.

## Endpoints

```text
GET /api/app/android/latest
GET /api/app/android/download
```

La metadata se cachea cinco minutos por instancia. El APK no se cachea, no se escribe a disco y no se carga completo en RAM.

Para repositorios privados usar un fine-grained PAT limitado al repositorio Android con permiso `Contents: read`. En repositorios públicos el token es opcional, aunque mejora el límite de solicitudes.

## Prueba local

```powershell
python manage.py test api.tests_android_releases --verbosity=2
python manage.py runserver
Invoke-WebRequest http://127.0.0.1:8000/api/app/android/latest
```

Si todavía no existe una Release con `paola-psicope.apk`, el resultado correcto es HTTP 404; no se deben inventar versiones ni archivos.
