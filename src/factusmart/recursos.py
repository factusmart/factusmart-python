"""Recursos del API: cuenta, series, comprobantes, anulaciones, guías, RUCs, anexos y catálogos.

Los datos (payload y respuesta) van tal cual los define el API, con las claves
en español. El SDK no las traduce.
"""

from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Sequence, Union

if TYPE_CHECKING:  # pragma: no cover
    from .cliente import Cliente

__all__ = [
    "Cuenta",
    "Series",
    "Comprobantes",
    "Anulaciones",
    "Guias",
    "Rucs",
    "Establecimientos",
    "Catalogos",
    "TIPOS_DE_ARCHIVO",
    "FORMATOS_PDF",
]

#: Archivos que se pueden descargar de un comprobante.
TIPOS_DE_ARCHIVO = ("pdf", "xml", "cdr")

#: Tamaños del PDF (``formato``): ``ticket`` es lo mismo que ``ticket80`` (80 mm).
FORMATOS_PDF = ("a4", "a5", "ticket", "ticket80", "ticket58", "ticket50")


def _formato_invalido(mensaje: str) -> Exception:
    from .errores import CodigoDeError, ErrorDeValidacion

    return ErrorDeValidacion(
        mensaje,
        status=422,
        codigo=CodigoDeError.DATOS_INVALIDOS,
        reintentable=False,
        campos={"formato": [mensaje]},
    )


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

    def descargar(
        self,
        external_id: str,
        tipo: str,
        ruc: Optional[str] = None,
        formato: Optional[str] = None,
    ) -> bytes:
        """Descarga el ``pdf``, ``xml`` o ``cdr`` del comprobante. Devuelve ``bytes``.

        ``formato`` (solo para ``pdf``): ``a4``, ``a5``, ``ticket`` (= ``ticket80``,
        80 mm), ``ticket80``, ``ticket58`` o ``ticket50``. Sin ``formato`` llega
        el A4 de siempre. ``formato`` con ``xml``/``cdr`` o un valor fuera de la
        lista lanza :class:`~factusmart.ErrorDeValidacion` sin hacer la petición.
        """
        tipo = str(tipo).lower()
        if tipo not in TIPOS_DE_ARCHIVO:
            raise ValueError("tipo debe ser 'pdf', 'xml' o 'cdr' (recibido: {!r}).".format(tipo))
        query: Dict[str, Any] = {}
        if formato is not None:
            if tipo != "pdf":
                raise _formato_invalido("formato solo aplica al PDF (tipo recibido: {!r}).".format(tipo))
            valor = str(formato).lower()
            if valor not in FORMATOS_PDF:
                raise _formato_invalido(
                    "formato debe ser uno de: {} (recibido: {!r}).".format(", ".join(FORMATOS_PDF), formato)
                )
            query["formato"] = valor
        ruta = "/documents/{}/{}".format(self._c._segmento(external_id), tipo)
        return self._c._get(ruta, ruc=self._c._ruc(ruc), query=query, binario=True)

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

    def calcular(
        self,
        items: Sequence[Mapping[str, Any]],
        porcentaje_igv: Optional[Union[int, float]] = None,
    ) -> Dict[str, Any]:
        """Calcula ``items`` y ``totales`` en el servidor sin emitir (``POST /calcular``).

        No emite ni consume crédito y no lleva RUC. Cada ítem trae
        ``descripcion``, ``cantidad``, ``afectacion`` y ``valor_unitario`` (sin
        IGV) **o** ``precio_unitario`` (con IGV: respeta lo que paga el cliente,
        3 × S/ 10.00 = S/ 30.00). ``porcentaje_igv``: 18 (por defecto) o 10.5
        (tasa reducida, Ley 31556).

        Devuelve la respuesta tal cual (``success``, ``items``, ``totales``),
        lista para copiar ``items`` y ``totales`` en :meth:`emitir`. Como no
        tiene efectos, se reintenta igual que una consulta GET. Para calcular
        sin red (solo ``valor_unitario`` y 18 %) usa
        :func:`factusmart.calcular_comprobante`.
        """
        cuerpo: Dict[str, Any] = {"items": [dict(i) for i in items]}
        if porcentaje_igv is not None:
            cuerpo["porcentaje_igv"] = porcentaje_igv
        return self._c._peticion("POST", "/calcular", cuerpo=cuerpo, reintentable=True)


class Anulaciones(_Recurso):
    def crear(self, datos: Mapping[str, Any], ruc: Optional[str] = None) -> Dict[str, Any]:
        """Anula facturas o boletas (``POST /anulaciones``). Nunca se reintenta sola.

        El API elige el camino: facturas (y sus notas) van por comunicación de
        baja (``tipo: "baja"``, ``identificador`` ``RA-…``); boletas (y sus
        notas, solo las aceptadas, estado ``05``) por resumen diario
        (``tipo: "resumen"``, ``identificador`` ``RC-…``). Facturas y boletas
        juntas → ``ErrorDeValidacion`` con ``codigo`` ``ANULACION_MIXTA``: haz
        una petición por tipo.

        La respuesta trae ``tipo``, ``identificador``, ``ticket``,
        ``external_id``, ``creditos_restantes``, ``credito_cobrado`` y, en RUCs
        demo (sin costo), ``modo_demo`` y ``pruebas_restantes_hoy``. Cuesta 1
        crédito salvo en demo.

        ``fecha_de_emision_de_documentos`` va en formato DD-MM-AAAA.
        """
        return self._c._peticion("POST", "/anulaciones", cuerpo=self._c._cuerpo_con_ruc(datos, ruc))

    def estado(self, ticket: str, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Resultado de la anulación en SUNAT (``GET /anulaciones/{ticket}/status``).

        Trae también ``tipo`` (``baja`` | ``resumen``) y ``documentos``.
        """
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


class Establecimientos(_Recurso):
    """Locales (anexos SUNAT) del RUC. No consumen crédito."""

    def listar(self, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Locales del RUC con su ``codigo_anexo`` y series (``GET /establecimientos``).

        Trae ``success`` y ``establecimientos``; ``predeterminado: True`` marca el
        local desde donde emite :meth:`Comprobantes.emitir` si no mandas
        ``codigo_anexo``. Es una consulta: se reintenta como cualquier GET.
        """
        return self._c._get("/establecimientos", ruc=self._c._ruc(ruc))

    def crear(self, datos: Mapping[str, Any], ruc: Optional[str] = None) -> Dict[str, Any]:
        """Crea un local (``POST /establecimientos``). Nunca se reintenta sola.

        ``datos``: ``codigo_anexo`` (4 dígitos, regístralo antes en SUNAT),
        ``nombre``, ``direccion``, ``ubigeo`` y opcionales ``telefono``,
        ``email``, ``crear_series_por_defecto`` (``True`` por defecto) y
        ``series`` (``[{"codigo_tipo_documento": "03", "serie": "B002"}]``).
        Si el plan no admite más locales: :class:`~factusmart.RucNoAutorizado`
        con ``codigo`` ``LIMITE_ESTABLECIMIENTOS``. Editar o eliminar un local
        solo desde el sistema web.
        """
        return self._c._peticion("POST", "/establecimientos", cuerpo=self._c._cuerpo_con_ruc(datos, ruc))


class Catalogos(_Recurso):
    """Catálogos SUNAT (unidades, afectación del IGV, monedas…). No consumen crédito."""

    def listar(self, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Catálogos disponibles (``GET /catalogos``): trae ``catalogos`` y ``nota``."""
        return self._c._get("/catalogos", ruc=self._c._ruc(ruc))

    def consultar(self, nombre: str, q: Optional[str] = None, ruc: Optional[str] = None) -> Dict[str, Any]:
        """Filas de un catálogo (``GET /catalogos/{nombre}``).

        ``nombre``: el nombre (``"unidades"``) o el número SUNAT (``"03"``).
        ``q`` filtra por código o descripción. Con ``ruc`` se lee el catálogo
        de ese RUC: usa solo las filas con ``activo: True``.
        Devuelve ``catalogo``, ``total`` y ``datos``.
        """
        ruta = "/catalogos/" + self._c._segmento(nombre)
        return self._c._get(ruta, ruc=self._c._ruc(ruc), query={"q": q})

    def buscar_producto_sunat(
        self,
        q: str,
        limite: Optional[int] = None,
        ruc: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Busca el código de producto SUNAT (catálogo 25) (``GET /catalogos/productos-sunat``).

        ``q``: código (exacto o prefijo, ``"4321"``) o texto (sin importar
        tildes, ``"computador"``). ``limite``: cuántas filas (máx. 50).
        Devuelve ``catalogo``, ``catalogo_sunat`` (``"25"``), ``q``, ``total``,
        ``hay_mas`` y ``datos`` (``[{"codigo": ..., "descripcion": ...}]``).
        Es una consulta: se reintenta como cualquier GET.
        """
        return self._c._get(
            "/catalogos/productos-sunat",
            ruc=self._c._ruc(ruc),
            query={"q": q, "limite": limite},
        )
