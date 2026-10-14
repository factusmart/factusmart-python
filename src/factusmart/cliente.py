"""Cliente HTTP del API de facturación de FactuSmart (solo librería estándar)."""

import json
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from ._version import __version__
from .errores import (
    ErrorDeAutenticacion,
    ErrorDeValidacion,
    FactuSmartError,
    LimiteDePeticiones,
    NoEncontrado,
    RucNoAutorizado,
    SinCreditos,
)
from .webhooks import verificar_firma_webhook as _verificar_firma_webhook

__all__ = ["Cliente", "Transporte", "OPERACIONES", "hora_peru"]

#: Firma del transporte HTTP. Recibe (metodo, url, headers, cuerpo, timeout,
#: contexto_ssl) y devuelve (status, headers, cuerpo). Ante un error de red
#: debe lanzar ``OSError`` (``urllib.error.URLError``, ``socket.timeout``...).
Transporte = Callable[
    [str, str, Dict[str, str], Optional[bytes], float, Optional[ssl.SSLContext]],
    Tuple[int, Dict[str, str], bytes],
]

#: operationId del archivo openapi.yaml -> método del SDK.
OPERACIONES: Dict[str, str] = {
    "ping": "ping",
    "getAccount": "cuenta.saldo",
    "listSeries": "series.listar",
    "emitDocument": "comprobantes.emitir",
    "listDocuments": "comprobantes.listar",
    "getDocument": "comprobantes.consultar",
    "downloadDocumentFile": "comprobantes.descargar",
    "resendDocument": "comprobantes.reenviar",
    "querySunatStatus": "comprobantes.consultar_sunat",
    "getDocumentHistory": "comprobantes.historial",
    "voidDocument": "anulaciones.crear",
    "getVoidStatus": "anulaciones.estado",
    "emitDispatchGuide": "guias.emitir",
    "getDispatchGuideStatus": "guias.estado",
    "listRucs": "rucs.listar",
    "createRuc": "rucs.crear",
    "setRucActivation": "rucs.activar",
    "listEstablishments": "establecimientos.listar",
    "createEstablishment": "establecimientos.crear",
    "calculateDocument": "comprobantes.calcular",
    "listCatalogs": "catalogos.listar",
    "getCatalog": "catalogos.consultar",
    "searchSunatProductCodes": "catalogos.buscar_producto_sunat",
    # Webhook: FactuSmart llama a TU servidor; el SDK solo verifica la firma.
    "webhookComprobanteEstado": "verificar_firma_webhook",
}

# Perú no tiene horario de verano: UTC-5 fijo (funciona en Python 3.8 y en
# Windows sin el paquete tzdata, a diferencia de zoneinfo).
_ZONA_PERU = timezone(timedelta(hours=-5), "America/Lima")

_REINTENTABLES = frozenset({429, 502, 503, 504})
_ESPERA_MAXIMA = 60.0


def hora_peru() -> datetime:
    """Fecha y hora actuales de Perú (America/Lima, UTC-5)."""
    return datetime.now(_ZONA_PERU)


def _transporte_urllib(
    metodo: str,
    url: str,
    headers: Dict[str, str],
    cuerpo: Optional[bytes],
    timeout: float,
    contexto: Optional[ssl.SSLContext],
) -> Tuple[int, Dict[str, str], bytes]:
    req = urllib.request.Request(url, data=cuerpo, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=contexto) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        cabeceras = {k.lower(): v for k, v in e.headers.items()} if e.headers else {}
        try:
            datos = e.read()
        except Exception:  # pragma: no cover - cuerpo ilegible
            datos = b""
        return e.code, cabeceras, datos


def _decodificar(cuerpo: bytes) -> Any:
    if not cuerpo:
        return None
    texto = cuerpo.decode("utf-8", errors="replace")
    try:
        return json.loads(texto)
    except ValueError:
        return texto


def _mensaje_de(cuerpo: Any, status: int) -> str:
    """Saca un mensaje legible de cualquiera de las formas de error del API."""
    if isinstance(cuerpo, dict):
        msg = cuerpo.get("message", cuerpo.get("mensaje"))
        if isinstance(msg, str) and msg.strip():
            return msg
        mapa = msg if isinstance(msg, dict) else cuerpo
        partes = []
        for campo, errores in mapa.items():
            if campo in ("success", "file", "line"):
                continue
            if isinstance(errores, (list, tuple)):
                partes.append("{}: {}".format(campo, " ".join(str(e) for e in errores)))
            elif isinstance(errores, str):
                partes.append("{}: {}".format(campo, errores))
        if partes:
            return "; ".join(partes)
    if status == 404:
        return "No encontrado (HTTP 404)."
    return "Error HTTP {} del API de FactuSmart.".format(status)


def _es_limite(status: int, cuerpo: Any) -> bool:
    if status == 429:
        return True
    # El API actual convierte el 429 en 500 "Too Many Attempts." (ver openapi.yaml).
    return (
        status == 500
        and isinstance(cuerpo, dict)
        and isinstance(cuerpo.get("message"), str)
        and "too many attempts" in cuerpo["message"].lower()
    )


def _segundos_de_espera(headers: Mapping[str, str], cuerpo: Any) -> Optional[float]:
    valor = headers.get("retry-after")
    if valor:
        try:
            return max(0.0, float(valor.strip()))
        except ValueError:
            pass
    if isinstance(cuerpo, dict):
        segundos = cuerpo.get("retry_after")
        if isinstance(segundos, (int, float)) and not isinstance(segundos, bool) and segundos >= 0:
            return float(segundos)
        msg = cuerpo.get("message")
        if isinstance(msg, str):
            m = re.search(r"espera\s+(\d+(?:[.,]\d+)?)\s*segundo", msg, re.IGNORECASE)
            if m:
                return float(m.group(1).replace(",", "."))
    return None


def _pide_reintento(cuerpo: Any) -> bool:
    """El servidor marca el error como reintentable (``"reintentable": true``)."""
    return isinstance(cuerpo, dict) and cuerpo.get("reintentable") is True


def _prohibe_reintento(cuerpo: Any) -> bool:
    """El servidor dice ``"reintentable": false``: manda sobre la regla por HTTP.

    Caso real: 429 ``LIMITE_PRUEBAS_DIARIO`` (tope diario de pruebas en RUCs demo,
    se reinicia a medianoche de Lima): repetir no sirve hasta el día siguiente.
    """
    return isinstance(cuerpo, dict) and cuerpo.get("reintentable") is False


def _error_http(status: int, headers: Mapping[str, str], cuerpo: Any) -> FactuSmartError:
    mensaje = _mensaje_de(cuerpo, status)
    if _es_limite(status, cuerpo):
        return LimiteDePeticiones(mensaje, status, cuerpo, _segundos_de_espera(headers, cuerpo))
    clase = {
        401: ErrorDeAutenticacion,
        402: SinCreditos,
        403: RucNoAutorizado,
        404: NoEncontrado,
        422: ErrorDeValidacion,
    }.get(status, FactuSmartError)
    return clase(mensaje, status, cuerpo)


class Cliente:
    """Cliente del API de facturación electrónica de FactuSmart.

    >>> fs = Cliente(api_key="TU_API_KEY", base_url="https://TU_URL_BASE/api/v1/issuer", ruc="20123456789")
    >>> fs.ping()["success"]
    True

    :param api_key: tu API key (va en el header ``X-API-Key``).
    :param base_url: URL base de tu cuenta (cada cuenta vive en un servidor distinto).
    :param ruc: RUC emisor por defecto. Se puede cambiar en cada llamada con ``ruc=``.
    :param timeout: segundos de espera por petición (SUNAT a veces tarda).
    :param max_reintentos: reintentos ante error de red, 429, 502, 503, 504 o una
        respuesta con ``"reintentable": true`` (solo en operaciones seguras de repetir).
        Una respuesta con ``"reintentable": false`` no se repite nunca.
    :param verificar_ssl: ``False`` solo para pruebas locales con certificado propio.
    :param transporte: función HTTP alternativa (pruebas o proxies). Ver :data:`Transporte`.
    :param dormir: función de espera (por defecto ``time.sleep``); útil en pruebas.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        ruc: Optional[str] = None,
        timeout: float = 60,
        max_reintentos: int = 3,
        verificar_ssl: bool = True,
        transporte: Optional[Transporte] = None,
        dormir: Optional[Callable[[float], None]] = None,
    ) -> None:
        if not api_key or not str(api_key).strip():
            raise ValueError("Falta api_key: es tu API key de FactuSmart (panel de integrador, pestaña Configuración).")
        if not base_url or not str(base_url).strip():
            raise ValueError(
                "Falta base_url: es la URL base de tu cuenta, por ejemplo "
                "https://s2.factusmart.pe/api/v1/issuer (aparece en tu panel de integrador)."
            )
        if max_reintentos < 0:
            raise ValueError("max_reintentos no puede ser negativo.")
        self.api_key: str = str(api_key).strip()
        self.base_url: str = str(base_url).strip().rstrip("/")
        self.ruc: Optional[str] = str(ruc) if ruc else None
        self.timeout: float = timeout
        self.max_reintentos: int = max_reintentos
        self.verificar_ssl: bool = verificar_ssl
        self._transporte: Transporte = transporte or _transporte_urllib
        self._dormir: Callable[[float], None] = dormir or time.sleep
        self._contexto: Optional[ssl.SSLContext] = None
        if not verificar_ssl:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            self._contexto = ctx

        # Imports aquí para evitar ciclos.
        from .recursos import Anulaciones, Catalogos, Comprobantes, Cuenta, Establecimientos, Guias, Rucs, Series

        self.cuenta = Cuenta(self)
        self.series = Series(self)
        self.comprobantes = Comprobantes(self)
        self.anulaciones = Anulaciones(self)
        self.guias = Guias(self)
        self.rucs = Rucs(self)
        self.establecimientos = Establecimientos(self)
        self.catalogos = Catalogos(self)

    def __repr__(self) -> str:
        return "Cliente(base_url={!r}, ruc={!r})".format(self.base_url, self.ruc)

    # ------------------------------------------------------------------ ping
    def ping(self, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Prueba la API key y devuelve el saldo (no consume crédito)."""
        return self._get("/ping", ruc=self._ruc(ruc))

    # ------------------------------------------------------------- webhooks
    @staticmethod
    def verificar_firma_webhook(cuerpo_crudo: Any, firma: Any, secreto: Any) -> bool:
        """Igual que :func:`factusmart.verificar_firma_webhook`."""
        return _verificar_firma_webhook(cuerpo_crudo, firma, secreto)

    # ------------------------------------------------------------- internos
    def _ruc(self, ruc: Optional[str]) -> Optional[str]:
        return str(ruc) if ruc else self.ruc

    def _cuerpo_con_ruc(self, datos: Optional[Mapping[str, Any]], ruc: Optional[str]) -> Dict[str, Any]:
        cuerpo = dict(datos or {})
        r = self._ruc(ruc)
        if r and not cuerpo.get("ruc"):
            cuerpo["ruc"] = r
        return cuerpo

    def _get(
        self,
        ruta: str,
        ruc: Optional[str] = None,
        query: Optional[Mapping[str, Any]] = None,
        binario: bool = False,
    ) -> Any:
        q: Dict[str, Any] = {}
        if ruc:
            q["ruc"] = ruc
        for k, v in (query or {}).items():
            if v is not None:
                q[k] = v
        return self._peticion("GET", ruta, query=q, reintentable=True, binario=binario)

    def _peticion(
        self,
        metodo: str,
        ruta: str,
        query: Optional[Mapping[str, Any]] = None,
        cuerpo: Any = None,
        headers: Optional[Mapping[str, str]] = None,
        reintentable: bool = False,
        reintentar_409: bool = False,
        binario: bool = False,
    ) -> Any:
        url = self.base_url + ruta
        if query:
            url += "?" + urllib.parse.urlencode(query)
        cabeceras: Dict[str, str] = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "factusmart-python/{}".format(__version__),
        }
        datos: Optional[bytes] = None
        if cuerpo is not None:
            datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
            cabeceras["Content-Type"] = "application/json; charset=utf-8"
        if headers:
            cabeceras.update(headers)

        intentos = 1 + (self.max_reintentos if reintentable else 0)
        for intento in range(intentos):
            ultimo = intento == intentos - 1
            espera_base = float(2 ** intento)  # 1 s, 2 s, 4 s...
            try:
                status, resp_headers, resp_cuerpo = self._transporte(
                    metodo, url, dict(cabeceras), datos, self.timeout, self._contexto
                )
            except (OSError, socket.timeout) as e:  # URLError hereda de OSError
                certificado = isinstance(e, ssl.SSLCertVerificationError) or isinstance(
                    getattr(e, "reason", None), ssl.SSLCertVerificationError
                )
                if ultimo or certificado:
                    motivo = getattr(e, "reason", None) or e
                    raise FactuSmartError(
                        "No se pudo conectar con FactuSmart ({}): {}".format(self.base_url, motivo)
                    ) from e
                self._dormir(espera_base)
                continue

            resp_headers = {k.lower(): v for k, v in (resp_headers or {}).items()}

            if 200 <= status < 300:
                if binario:
                    return resp_cuerpo
                return _decodificar(resp_cuerpo)

            decodificado = _decodificar(resp_cuerpo)
            # Solo llega aquí con más de un intento si la operación es segura de
            # repetir (``reintentable=True``): las prohibidas nunca se repiten,
            # aunque el servidor diga ``"reintentable": true``.
            # ``"reintentable": false`` en el cuerpo manda: no se repite nunca,
            # aunque el HTTP sea 429/409/5xx. Sin ese campo, regla por HTTP.
            puede_reintentar = not _prohibe_reintento(decodificado) and (
                status in _REINTENTABLES
                or _es_limite(status, decodificado)
                or (reintentar_409 and status == 409)
                or _pide_reintento(decodificado)
            )
            if puede_reintentar and not ultimo:
                espera = espera_base
                if _es_limite(status, decodificado):
                    leida = _segundos_de_espera(resp_headers, decodificado)
                    if leida is not None:
                        espera = leida
                self._dormir(min(espera, _ESPERA_MAXIMA))
                continue
            raise _error_http(status, resp_headers, decodificado)

        raise FactuSmartError("Se agotaron los reintentos.")  # pragma: no cover

    @staticmethod
    def _nueva_idempotency_key() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _segmento(valor: Any) -> str:
        texto = str(valor)
        if not texto:
            raise ValueError("El identificador no puede estar vacío.")
        return urllib.parse.quote(texto, safe="")
