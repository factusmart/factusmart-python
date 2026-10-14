"""Excepciones del SDK de FactuSmart.

Todas heredan de :class:`FactuSmartError`, que trae:

- ``status``: código HTTP (``None`` si fue un error de red).
- ``mensaje``: el ``message`` del API, legible y en español.
- ``respuesta``: el cuerpo completo de la respuesta (dict, o texto si no era JSON).

Importante: un HTTP 200 con ``aceptado_por_sunat: False`` NO lanza ninguna
excepción. Es un resultado normal que tu sistema debe revisar.
"""

from typing import Any, Optional

__all__ = [
    "FactuSmartError",
    "ErrorDeAutenticacion",
    "SinCreditos",
    "RucNoAutorizado",
    "NoEncontrado",
    "ErrorDeValidacion",
    "LimiteDePeticiones",
]


class FactuSmartError(Exception):
    """Error base del SDK (también se usa para errores de red y HTTP no mapeados)."""

    def __init__(self, mensaje: str, status: Optional[int] = None, respuesta: Any = None) -> None:
        super().__init__(mensaje)
        self.mensaje: str = mensaje
        self.status: Optional[int] = status
        self.respuesta: Any = respuesta

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
