"""Ayudante para calcular IGV y totales de un comprobante.

Usa ``decimal.Decimal`` con redondeo ROUND_HALF_UP (el "redondeo de colegio")
para que el resultado sea idéntico al de los SDK de PHP y Node, sin errores de
coma flotante. El resultado se devuelve como ``float`` con 2 decimales.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Mapping, Sequence, Union

__all__ = ["calcular_comprobante", "AFECTACIONES_SOPORTADAS"]

Numero = Union[int, float, str, Decimal]

_IGV = Decimal("0.18")
_CENTIMO = Decimal("0.01")
_CERO = Decimal("0")

#: 10 gravado (18%), 20 exonerado, 30 inafecto, 40 exportación.
AFECTACIONES_SOPORTADAS = ("10", "20", "30", "40")


def _dec(valor: Numero) -> Decimal:
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, bool):
        raise TypeError("Se esperaba un número, no un booleano.")
    # str() evita arrastrar el error binario del float (10.555 -> "10.555").
    return Decimal(str(valor))


def _r2(valor: Decimal) -> Decimal:
    return valor.quantize(_CENTIMO, rounding=ROUND_HALF_UP)


def _f(valor: Decimal) -> float:
    return float(_r2(valor))


def calcular_comprobante(items: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Calcula ``items`` y ``totales`` listos para ``comprobantes.emitir``.

    Cada ítem de entrada lleva: ``descripcion``, ``cantidad``, ``valor_unitario``
    (SIN IGV), ``afectacion`` (``"10"``, ``"20"``, ``"30"`` o ``"40"``) y,
    opcionales, ``codigo_interno`` y ``unidad_de_medida`` (por defecto ``NIU``).

    Redondea a 2 decimales por ítem, igual que la función de la documentación
    pública ("Calcular IGV y totales").

    Devuelve ``{"items": [...], "totales": {...}}``.
    """
    if not items:
        raise ValueError("calcular_comprobante necesita al menos un ítem.")

    gravadas = exoneradas = inafectas = exportacion = total_igv = _CERO
    items_api: List[Dict[str, Any]] = []

    for i, it in enumerate(items, start=1):
        for campo in ("descripcion", "cantidad", "valor_unitario", "afectacion"):
            if campo not in it or it[campo] is None:
                raise ValueError("Ítem {}: falta el campo '{}'.".format(i, campo))
        afectacion = str(it["afectacion"])
        if afectacion not in AFECTACIONES_SOPORTADAS:
            raise ValueError(
                "Ítem {}: afectación '{}' no soportada por el ayudante "
                "(usa 10, 20, 30 o 40; para otras arma el ítem a mano).".format(i, afectacion)
            )

        cantidad = _dec(it["cantidad"])
        valor_unitario = _dec(it["valor_unitario"])
        gravado = afectacion == "10"

        base = _r2(valor_unitario * cantidad)
        igv = _r2(base * _IGV) if gravado else _CERO

        if gravado:
            gravadas += base
        elif afectacion == "20":
            exoneradas += base
        elif afectacion == "30":
            inafectas += base
        else:
            exportacion += base
        total_igv += igv

        item: Dict[str, Any] = {}
        if it.get("codigo_interno") is not None:
            item["codigo_interno"] = it["codigo_interno"]
        item.update(
            {
                "descripcion": it["descripcion"],
                "unidad_de_medida": it.get("unidad_de_medida") or "NIU",
                "cantidad": it["cantidad"],
                "valor_unitario": _f(valor_unitario),
                "codigo_tipo_precio": "01",
                "precio_unitario": _f(valor_unitario * (Decimal(1) + _IGV if gravado else Decimal(1))),
                "codigo_tipo_afectacion_igv": afectacion,
                "total_base_igv": _f(base),
                "porcentaje_igv": 18 if gravado else 0,
                "total_igv": _f(igv),
                "total_impuestos": _f(igv),
                "total_valor_item": _f(base),
                "total_item": _f(base + igv),
            }
        )
        items_api.append(item)

    total_valor = _r2(gravadas + exoneradas + inafectas + exportacion)
    return {
        "items": items_api,
        "totales": {
            "total_operaciones_gravadas": _f(gravadas),
            "total_operaciones_exoneradas": _f(exoneradas),
            "total_operaciones_inafectas": _f(inafectas),
            "total_exportacion": _f(exportacion),
            "total_igv": _f(total_igv),
            "total_impuestos": _f(total_igv),
            "total_valor": _f(total_valor),
            "total_venta": _f(total_valor + total_igv),
        },
    }
