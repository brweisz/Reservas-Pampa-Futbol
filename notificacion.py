import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def enviar_notificacion(clase: dict):
    mail_from = os.environ["MAIL_FROM"]
    mail_password = os.environ["MAIL_PASSWORD"]
    mail_to = os.environ["MAIL_TO"]
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))

    cuerpo = (
        f"Tu clase fue reservada automáticamente.\n\n"
        f"Fecha:         {clase['fecha']}\n"
        f"Nivel:         {clase['nivel']}\n"
        f"Sede:          {clase['sede']}\n"
        f"Ver próximas clases:\n"
        f"https://www.pampafutbol.com/alumno/proximas-clases\n"
    )

    msg = MIMEMultipart()
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Subject"] = "Clase de Pampa reservada automaticamente"
    msg.attach(MIMEText(cuerpo, "plain"))

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.starttls()
        smtp.login(mail_from, mail_password)
        smtp.send_message(msg)
