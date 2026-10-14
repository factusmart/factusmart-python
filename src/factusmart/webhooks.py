"""Verificación de la firma de los webhooks de FactuSmart.

FactuSmart firma cada aviso con el header ``X-FactuSmart-Firma``: el
HMAC-SHA256, en hexadecimal minúscula y sin prefijo, del **cuerpo crudo** de
la petición usando tu secreto ``whsec_…``.
"""

import hashlib
import hmac
import re
from typing import Any

__all__ = ["verificar_firma_webhook", "HEADER_FIRMA"]

#: Nombre del header que trae la firma.
HEADER_FIRMA = "X-FactuSmart-Firma"

_HEX64 = re.compile(r"[0-9a-f]{64}")


def _a_bytes(valor: Any) -> Any:
    if isinstance(valor, (bytes, bytearray)):
        return bytes(valor)
    if isinstance(valor, str):
        return valor.encode("utf-8")
    return None


def verificar_firma_webhook(cuerpo_crudo: Any, firma: Any, secreto: Any) -> bool:
    """``True`` si ``firma`` es la firma correcta de ``cuerpo_crudo`` con ``secreto``.

    :param cuerpo_crudo: el cuerpo TAL CUAL llegó (``bytes`` o ``str`` UTF-8).
        No uses el JSON ya parseado y vuelto a serializar: cambia los bytes y
        la firma no coincide.
    :param firma: el valor del header ``X-FactuSmart-Firma`` (64 caracteres hex).
    :param secreto: tu secreto ``whsec_…`` del portal (``str`` o ``bytes``).

    Nunca lanza excepción: ante datos vacíos, ``None``, tipos raros o una firma
    mal formada devuelve ``False``. Compara en tiempo constante.
    """
    try:
        cuerpo = _a_bytes(cuerpo_crudo)
        clave = _a_bytes(secreto)
        if cuerpo is None or not clave:
            return False
        if isinstance(firma, (bytes, bytearray)):
            firma = bytes(firma).decode("ascii")
        if not isinstance(firma, str):
            return False
        firma = firma.strip().lower()
        if not _HEX64.fullmatch(firma):
            return False
        esperada = hmac.new(clave, cuerpo, hashlib.sha256).hexdigest()
        return hmac.compare_digest(esperada, firma)
    except Exception:
        return False
