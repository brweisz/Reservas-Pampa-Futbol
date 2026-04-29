# Bot de reservas - Pampa Futbol

Reserva automaticamente una clase en [pampafutbol.com](https://www.pampafutbol.com). Recarga la pagina cada 30 segundos hasta que se habilite un lugar, hace el click automaticamente y envia un mail de confirmacion.

Hay dos formas de usarlo: por terminal (CLI) o como web app (frontend + backend).

## Instalacion

```bash
bash setup.sh
```

En caso de error de permisos:

```bash
sudo chmod +x setup.sh
```

## Configuracion

Edita el archivo `.env` con tus datos:

```env
# Notificaciones por mail (requerido para ambos modos)
MAIL_FROM=tu@gmail.com
MAIL_PASSWORD=app_password_de_gmail

# Solo para modo CLI:
DOCUMENTO=12345678
PASSWORD=tupassword
MAIL_TO=tu@gmail.com

# Opcional
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
```

> **Nota para Gmail:** necesitas una *App Password*, no tu contrasena normal.
>
> 1. Activa la verificacion en dos pasos en tu cuenta Google
> 2. Entra a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
> 3. Genera una nueva app password (nombre libre, ej: "Pampa Bot")
> 4. Copia los 16 caracteres y pegalos en `MAIL_PASSWORD` (sin espacios)

## Uso: modo CLI

```bash
python bot.py
```

1. El bot inicia sesion y muestra todas las clases disponibles
2. Elegis el numero de la clase que queres reservar
3. El bot recarga la pagina cada 30 segundos hasta que haya lugar
4. Cuando se habilita un lugar, hace el click automaticamente
5. Se envia un mail de confirmacion con los datos de la clase

## Uso: modo web

Requiere Node.js para el frontend.

```bash
# Instalar dependencias del frontend (una sola vez)
cd frontend && npm install && cd ..

# Terminal 1: backend
uvicorn app.main:app --reload

# Terminal 2: frontend
cd frontend && npm run dev
```

Abri `http://localhost:5173` en el navegador.

1. Ingresa documento, contrasena y email de notificacion
2. Elegis la clase que queres reservar
3. El backend monitorea la pagina cada 30 segundos
4. Cuando se habilita un lugar, reserva automaticamente y envia el mail
