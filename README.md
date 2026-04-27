# Bot de reservas - Pampa Fútbol

Reserva automáticamente una clase en [pampafutbol.com](https://www.pampafutbol.com). Recarga la página cada 30 segundos hasta que se habilite un lugar, hace el click automáticamente y envía un mail de confirmación.

## Instalación

```bash
bash setup.sh
```
o
```bash
./setup.sh
```

En caso de error de permisos, ejecutar antes:

```bash
sudo chmod +x setup.sh
```

## Configuración

Editá el archivo `.env` con tus datos:

```env
# Credenciales de Pampa Fútbol
DOCUMENTO=12345678
PASSWORD=tupassword

# Notificaciones por mail
MAIL_FROM=tu@gmail.com
MAIL_PASSWORD=app_password_de_gmail
MAIL_TO=tu@gmail.com
# SMTP_HOST=smtp.gmail.com  # opcional, por defecto Gmail
# SMTP_PORT=587              # opcional
```

> **Nota para Gmail:** necesitás una *App Password*, no tu contraseña normal.
>
> 1. Activá la verificación en dos pasos en tu cuenta Google (si no la tenés)
> 2. Entrá a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
> 3. Generá una nueva app password (el nombre es libre, ej: "Pampa Bot")
> 4. Copiá los 16 caracteres generados y pegálos en `MAIL_PASSWORD` (sin espacios)

## Uso

```bash
python bot.py
```

1. El bot inicia sesión y muestra todas las clases disponibles
2. Elegís el número de la clase que querés reservar
3. El bot recarga la página cada 30 segundos hasta que haya lugar
4. Cuando se habilita un lugar, hace el click automáticamente
5. Se envía un mail de confirmación con los datos de la clase
