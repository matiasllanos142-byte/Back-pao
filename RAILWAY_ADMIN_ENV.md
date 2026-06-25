# Variables de Railway para el admin

Estas variables van en el servicio backend de Railway.

```text
ADMIN_USERNAME=admin@paolapsicope.com
ADMIN_PASSWORD_HASH=pbkdf2_sha256$...
ADMIN_JWT_SECRET=una-clave-larga-y-distinta
ADMIN_TOKEN_TTL=86400
```

`ADMIN_PASSWORD_HASH` no es la contrasena plana. Generala localmente desde
PowerShell:

```powershell
$password = Read-Host "Password admin" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))
$env:DJANGO_ADMIN_PASSWORD = $plain
python manage.py shell -c "import os; from django.contrib.auth.hashers import make_password; print(make_password(os.environ['DJANGO_ADMIN_PASSWORD']))"
Remove-Variable password,plain -ErrorAction SilentlyContinue
Remove-Item Env:\DJANGO_ADMIN_PASSWORD -ErrorAction SilentlyContinue
```

Despues copia el hash resultante en Railway:

```powershell
railway variables --set "ADMIN_USERNAME=admin@paolapsicope.com"
railway variables --set "ADMIN_PASSWORD_HASH=pega-el-hash-generado"
railway variables --set "ADMIN_JWT_SECRET=una-clave-larga-y-distinta"
railway variables --set "ADMIN_TOKEN_TTL=86400"
```
