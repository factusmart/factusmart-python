"""Recursos del API: cuenta, series, comprobantes, anulaciones, guías y RUCs.

Los datos (payload y respuesta) van tal cual los define el API, con las claves
en español. El SDK no las traduce.
"""

from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional

if TYPE_CHECKING:  # pragma: no cover
    from .cliente import Cliente

__all__ = ["Cuenta", "Series", "Comprobantes", "Anulaciones", "Guias", "Rucs", "TIPOS_DE_ARCHIVO"]

#: Archivos que se pueden descargar de un comprobante.
TIPOS_DE_ARCHIVO = ("pdf", "xml", "cdr")


class _Recurso:
    def __init__(self, cliente: "Cliente") -> None:
        self._c = cliente


class Cuenta(_Recurso):
    def saldo(self) -> Dict[str, Any]:
        """Saldo, plan y RUCs de la cuenta (``GET /account``). No requiere RUC."""
        return self._c._get("/account")


class Series(_Recurso):
    def listar(self, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Series del RUC con el siguiente número estimado (``GET /series``)."""
        return self._c._get("/series", ruc=self._c._ruc(ruc))


class Comprobantes(_Recurso):
    def emitir(
        self,
        datos: Mapping[str, Any],
        ruc: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Emite una factura, boleta o nota (``POST /documents``). Cuesta 1 crédito.

        - Siempre manda ``Idempotency-Key`` (la tuya o un UUID v4) y reusa la
          MISMA en todos los reintentos: un reintento nunca emite dos veces.
        - Completa si faltan: ``numero_documento`` (``"#"``), ``fecha_de_emision``
          y ``hora_de_emision`` (hora de Perú), ``codigo_tipo_moneda`` (``PEN``)
          y, en facturas y boletas, ``codigo_tipo_operacion`` (``0101``).
        - Un 200 con ``aceptado_por_sunat: False`` NO lanza excepción: revísalo.
        """
        from .cliente import hora_peru

        cuerpo = self._c._cuerpo_con_ruc(datos, ruc)
        ahora = hora_peru()
        if not cuerpo.get("numero_documento"):
            cuerpo["numero_documento"] = "#"
        if not cuerpo.get("fecha_de_emision"):
            cuerpo["fecha_de_emision"] = ahora.strftime("%Y-%m-%d")
        if not cuerpo.get("hora_de_emision"):
            cuerpo["hora_de_emision"] = ahora.strftime("%H:%M:%S")
        if not cuerpo.get("codigo_tipo_moneda"):
            cuerpo["codigo_tipo_moneda"] = "PEN"
        # Según openapi.yaml, codigo_tipo_operacion "no aplica a notas" (07/08).
        if not cuerpo.get("codigo_tipo_operacion") and str(cuerpo.get("codigo_tipo_documento", "")) in ("01", "03"):
            cuerpo["codigo_tipo_operacion"] = "0101"

        clave = idempotency_key or self._c._nueva_idempotency_key()
        return self._c._peticion(
            "POST",
            "/documents",
            cuerpo=cuerpo,
            headers={"Idempotency-Key": str(clave)},
            reintentable=True,
            reintentar_409=True,
        )

    def listar(self, filtros: Optional[Mapping[str, Any]] = None, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Lista comprobantes (``GET /documents``).

        Filtros: ``estado``, ``desde``, ``hasta`` (YYYY-MM-DD), ``limite`` (1-100),
        ``antes_de`` (cursor: pasa el ``siguiente_cursor`` de la página anterior).
        """
        return self._c._get("/documents", ruc=self._c._ruc(ruc), query=filtros)

    def consultar(self, external_id: str, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Estado guardado del comprobante y sus links (``GET /documents/{external_id}``)."""
        return self._c._get("/documents/" + self._c._segmento(external_id), ruc=self._c._ruc(ruc))

    def descargar(self, external_id: str, tipo: str, ruc: Optional[str] = None) -> bytes:
        """Descarga el ``pdf``, ``xml`` o ``cdr`` del comprobante. Devuelve ``bytes``."""
        tipo = str(tipo).lower()
        if tipo not in TIPOS_DE_ARCHIVO:
            raise ValueError("tipo debe ser 'pdf', 'xml' o 'cdr' (recibido: {!r}).".format(tipo))
        ruta = "/documents/{}/{}".format(self._c._segmento(external_id), tipo)
        return self._c._get(ruta, ruc=self._c._ruc(ruc), binario=True)

    def reenviar(self, external_id: str, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Reintenta el envío a SUNAT (``POST .../reenviar``). Nunca se reintenta solo."""
        ruta = "/documents/{}/reenviar".format(self._c._segmento(external_id))
        return self._c._peticion("POST", ruta, cuerpo=self._c._cuerpo_con_ruc(None, ruc))

    def consultar_sunat(self, external_id: str, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Pregunta a SUNAT en vivo y sincroniza el estado (``POST .../consultar-sunat``)."""
        ruta = "/documents/{}/consultar-sunat".format(self._c._segmento(external_id))
        return self._c._peticion("POST", ruta, cuerpo=self._c._cuerpo_con_ruc(None, ruc))

    def historial(self, external_id: str, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Línea de tiempo del comprobante (``GET .../historial``)."""
        ruta = "/documents/{}/historial".format(self._c._segmento(external_id))
        return self._c._get(ruta, ruc=self._c._ruc(ruc))


class Anulaciones(_Recurso):
    def crear(self, datos: Mapping[str, Any], ruc: Optional[str] = None) -> Dict[str, Any]:
        """Comunicación de baja (``POST /anulaciones``). Cuesta 1 crédito. Nunca se reintenta sola.

        ``fecha_de_emision_de_documentos`` va en formato DD-MM-AAAA.
        """
        return self._c._peticion("POST", "/anulaciones", cuerpo=self._c._cuerpo_con_ruc(datos, ruc))

    def estado(self, ticket: str, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Resultado de la baja en SUNAT (``GET /anulaciones/{ticket}/status``)."""
        ruta = "/anulaciones/{}/status".format(self._c._segmento(ticket))
        return self._c._get(ruta, ruc=self._c._ruc(ruc))


class Guias(_Recurso):
    def emitir(self, datos: Mapping[str, Any], ruc: Optional[str] = None) -> Dict[str, Any]:
        """Emite una guía de remisión GRE 2.0 (``POST /guias``). No usa Idempotency-Key: nunca se reintenta sola.

        Completa si faltan ``numero_documento`` (``"#"``), ``fecha_de_emision`` y
        ``hora_de_emision`` (hora de Perú).
        """
        from .cliente import hora_peru

        cuerpo = self._c._cuerpo_con_ruc(datos, ruc)
        ahora = hora_peru()
        if not cuerpo.get("numero_documento"):
            cuerpo["numero_documento"] = "#"
        if not cuerpo.get("fecha_de_emision"):
            cuerpo["fecha_de_emision"] = ahora.strftime("%Y-%m-%d")
        if not cuerpo.get("hora_de_emision"):
            cuerpo["hora_de_emision"] = ahora.strftime("%H:%M:%S")
        return self._c._peticion("POST", "/guias", cuerpo=cuerpo)

    def estado(self, external_id: str, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Estado de la guía en SUNAT (``GET /guias/{external_id}/status``)."""
        ruta = "/guias/{}/status".format(self._c._segmento(external_id))
        return self._c._get(ruta, ruc=self._c._ruc(ruc))


class Rucs(_Recurso):
    """Gestión de los RUCs de la cuenta. Estos endpoints nunca llevan RUC emisor."""

    def listar(self) -> Dict[str, Any]:
        """RUCs de la cuenta con su entorno y si están activos (``GET /rucs``)."""
        return self._c._get("/rucs")

    def crear(self, datos: Mapping[str, Any]) -> Dict[str, Any]:
        """Alta de un RUC en modo prueba (``POST /rucs``).

        Necesita ``ruc``, ``empresa``, ``correo`` y ``clave``. El API lo hace
        idempotente por RUC (``ya_existia: True``), así que se reintenta ante
        errores de red, 429, 502, 503 y 504.
        """
        return self._c._peticion("POST", "/rucs", cuerpo=dict(datos), reintentable=True)

    def activar(self, ruc: str, activo: bool) -> Dict[str, Any]:
        """Activa (``True``) o desactiva (``False``) un RUC (``PATCH /rucs/{ruc}/activation``)."""
        ruta = "/rucs/{}/activation".format(self._c._segmento(ruc))
        return self._c._peticion("PATCH", ruta, cuerpo={"activo": bool(activo)})
