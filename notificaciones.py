"""Envío de avisos de validación por SMTP, configurado con variables de entorno."""

from email.message import EmailMessage
import os
import smtplib
import ssl


class ErrorNotificacion(RuntimeError):
    """Configuración o transporte de correo no disponible."""


def enviar_notificacion_aprobacion(destinatario, nombre, codigo, monto, estado='APROBADO'):
    """Envía el resultado de validación y retorna solo cuando SMTP lo acepta."""
    estado = str(estado or 'APROBADO').strip().upper()
    if estado not in {'APROBADO', 'DESCARTADO'}:
        raise ErrorNotificacion('El estado de notificación no está permitido.')
    host = os.environ.get('SMTP_HOST', '').strip()
    usuario = os.environ.get('SMTP_USER', '').strip()
    contrasena = os.environ.get('SMTP_PASSWORD', '')
    remitente = os.environ.get('SMTP_FROM', '').strip() or usuario
    if not host or not remitente:
        raise ErrorNotificacion(
            'El envío no está configurado. Define SMTP_HOST y SMTP_FROM (o SMTP_USER).'
        )
    if not destinatario or '@' not in destinatario:
        raise ErrorNotificacion('El registro no contiene un correo electrónico válido.')

    try:
        puerto = int(os.environ.get('SMTP_PORT', '587'))
        mensaje = EmailMessage()
        accion = 'aprobado' if estado == 'APROBADO' else 'rechazado'
        mensaje['Subject'] = f'Registro {codigo} {accion}'
        mensaje['From'] = remitente
        mensaje['To'] = destinatario
        mensaje.set_content(
            f'Hola {nombre or ""},\n\n'
            f'Tu registro {codigo} fue {accion}. Monto declarado: S/ {monto}.\n'
        )

        contexto = ssl.create_default_context()
        if puerto == 465:
            with smtplib.SMTP_SSL(
                host, puerto, timeout=20, context=contexto
            ) as servidor:
                if usuario:
                    servidor.login(usuario, contrasena)
                rechazados = servidor.send_message(mensaje)
        else:
            with smtplib.SMTP(host, puerto, timeout=20) as servidor:
                servidor.ehlo()
                servidor.starttls(context=contexto)
                servidor.ehlo()
                if usuario:
                    servidor.login(usuario, contrasena)
                rechazados = servidor.send_message(mensaje)
        if rechazados:
            raise ErrorNotificacion('El servidor de correo rechazó al destinatario.')
    except (OSError, smtplib.SMTPException, ValueError) as error:
        raise ErrorNotificacion('No se pudo confirmar el envío por correo.') from error

    return True
