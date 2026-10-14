"""Excepciones del SDK de FactuSmart.

Todas heredan de :class:`FactuSmartError`, que trae:

- ``status``: código HTTP (``None`` si fue un error de red).
- ``mensaje``: el ``message`` del API, legible y en español.
- ``respuesta``: el cuerpo completo de la respuesta (dict, o texto si no era JSON).
- ``codigo``: identificador estable del error en MAYÚSCULAS (``"NO_ENCONTRADO"``,
  ``"SIN_CREDITOS"``...). Decide tu lógica con este campo, no con ``mensaje``.
  ``None`` si no hubo respuesta (error de red) o el servidor no lo envía.
- ``reintentable``: ``True`` si repetir la MISMA petición más tarde puede
  funcionar; ``False`` si hay que corregir algo antes. ``None`` si el servidor
  no lo envía (versiones anteriores del API) o fue un error de red.
- ``campos``: en errores de validación (422), ``{campo: [mensajes]}``. ``{}``
  si no hay detalle por campo.

Importante: un HTTP 200 con ``aceptado_por_sunat: False`` NO lanza ninguna
excepción. Es un resultado normal que tu sistema debe revisar.
"""

from typing import Any, Dict, List, Optional

__all__ = [
    "CodigoDeError",
    "FactuSmartError",
    "ErrorDeAutenticacion",
    "SinCreditos",
    "RucNoAutorizado",
    "NoEncontrado",
    "ErrorDeValidacion",
    "LimiteDePeticiones",
]


class CodigoDeError:
    """Valores conocidos de :attr:`FactuSmartError.codigo`.

    La lista puede crecer (y existe el genérico ``"ERROR_<status>"``): trata un
    código desconocido como no reintentable salvo que ``reintentable`` diga lo
    contrario.
    """

    NO_AUTENTICADO = "NO_AUTENTICADO"
    PLAN_VENCIDO = "PLAN_VENCIDO"
    SIN_CREDITOS = "SIN_CREDITOS"
    RUC_NO_AUTORIZADO = "RUC_NO_AUTORIZADO"
    RUC_DESACTIVADO = "RUC_DESACTIVADO"
    SIN_PERMISO = "SIN_PERMISO"
    NO_ENCONTRADO = "NO_ENCONTRADO"
    RUTA_NO_ENCONTRADA = "RUTA_NO_ENCONTRADA"
    METODO_NO_PERMITIDO = "METODO_NO_PERMITIDO"
    EMISION_EN_CURSO = "EMISION_EN_CURSO"
    CONFLICTO = "CONFLICTO"
    DATOS_INVALIDOS = "DATOS_INVALIDOS"
    RUC_REQUERIDO = "RUC_REQUERIDO"
    RUC_SIN_TENANT = "RUC_SIN_TENANT"
    CERTIFICADO_NO_CONFIGURADO = "CERTIFICADO_NO_CONFIGURADO"
    ERROR_EMISION = "ERROR_EMISION"
    RECHAZADO_SUNAT = "RECHAZADO_SUNAT"
    REENVIO_FALLIDO = "REENVIO_FALLIDO"
    SUNAT_NO_DISPONIBLE = "SUNAT_NO_DISPONIBLE"
    LIMITE_PETICIONES = "LIMITE_PETICIONES"
    #: 429 no reintentable: tope diario de pruebas en RUCs demo (se reinicia a medianoche de Lima).
    LIMITE_PRUEBAS_DIARIO = "LIMITE_PRUEBAS_DIARIO"
    #: 422: facturas y boletas juntas en la misma anulación.
    ANULACION_MIXTA = "ANULACION_MIXTA"
    #: 403: llave de prueba usada contra un RUC en producción.
    LLAVE_DE_PRUEBA_EN_PRODUCCION = "LLAVE_DE_PRUEBA_EN_PRODUCCION"
    ERROR_INTERNO = "ERROR_INTERNO"
    #: 500 reintentable: el PDF en el ``formato`` pedido no se pudo generar.
    PDF_NO_GENERADO = "PDF_NO_GENERADO"
    #: 403: el plan del RUC no permite más locales (``establecimientos.crear``).
    LIMITE_ESTABLECIMIENTOS = "LIMITE_ESTABLECIMIENTOS"


def _codigo_de(respuesta: Any) -> Optional[str]:
    if isinstance(respuesta, dict):
        valor = respuesta.get("codigo")
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return None


def _reintentable_de(respuesta: Any) -> Optional[bool]:
    if isinstance(respuesta, dict):
        valor = respuesta.get("reintentable")
        if isinstance(valor, bool):
            return valor
    return None


def _campos_de(respuesta: Any) -> Dict[str, List[str]]:
    if not isinstance(respuesta, dict) or not isinstance(respuesta.get("campos"), dict):
        return {}
    campos: Dict[str, List[str]] = {}
    for campo, mensajes in respuesta["campos"].items():
        if isinstance(mensajes, (list, tuple)):
            campos[str(campo)] = [str(m) for m in mensajes]
        elif mensajes is not None:
            campos[str(campo)] = [str(mensajes)]
    return campos


class FactuSmartError(Exception):
    """Error base del SDK (también se usa para errores de red y HTTP no mapeados).

    ``codigo``, ``reintentable`` y ``campos`` se leen solos de ``respuesta``
    (si es un dict) cuando no se pasan explícitamente.
    """

    def __init__(
        self,
        mensaje: str,
        status: Optional[int] = None,
        respuesta: Any = None,
        codigo: Optional[str] = None,
        reintentable: Optional[bool] = None,
        campos: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        super().__init__(mensaje)
        self.mensaje: str = mensaje
        self.status: Optional[int] = status
        self.respuesta: Any = respuesta
        self.codigo: Optional[str] = codigo if codigo is not None else _codigo_de(respuesta)
        self.reintentable: Optional[bool] = reintentable if reintentable is not None else _reintentable_de(respuesta)
        self.campos: Dict[str, List[str]] = dict(campos) if campos is not None else _campos_de(respuesta)

    def __str__(self) -> str:
        if self.status is None:
            return self.mensaje
        return "HTTP {}: {}".format(self.status, self.mensaje)


class ErrorDeAutenticacion(FactuSmartError):
    """HTTP 401: API key ausente, inválida o cuenta desactivada."""


class SinCreditos(FactuSmartError):
    """HTTP 402: la cuenta no tiene créditos. No se emitió nada."""


class RucNoAutorizado(FactuSmartError):
    """HTTP 403: el RUC no pertenece a la cuenta o está desactivado."""


class NoEncontrado(FactuSmartError):
    """HTTP 404: el comprobante, guía, ticket o RUC no existe."""


class ErrorDeValidacion(FactuSmartError):
    """HTTP 422: datos inválidos o incompletos (el crédito no se cobra)."""


class LimiteDePeticiones(FactuSmartError):
    """Límite de peticiones superado (HTTP 429, o HTTP 500 "Too Many Attempts.").

    ``segundos_de_espera`` trae cuántos segundos esperar, si se pudo leer.

    Mira ``codigo``: con ``LIMITE_PRUEBAS_DIARIO`` (``reintentable=False``) se
    agotó el tope diario de pruebas del RUC demo y no sirve reintentar hasta
    medianoche de Lima; el SDK lo lanza tras una sola petición.
    """

    def __init__(
        self,
        mensaje: str,
        status: Optional[int] = None,
        respuesta: Any = None,
        segundos_de_espera: Optional[float] = None,
    ) -> None:
        super().__init__(mensaje, status, respuesta)
        self.segundos_de_espera: Optional[float] = segundos_de_espera
