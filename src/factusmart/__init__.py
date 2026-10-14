"""SDK de Python del API de facturación electrónica de FactuSmart (SUNAT, Perú).

Uso::

    import factusmart

    fs = factusmart.Cliente(api_key="TU_API_KEY", base_url="https://TU_URL_BASE/api/v1/issuer", ruc="20123456789")
    calc = factusmart.calcular_comprobante([
        {"descripcion": "Servicio de consultoría", "cantidad": 1, "valor_unitario": 100, "afectacion": "10"},
    ])
    r = fs.comprobantes.emitir({
        "codigo_tipo_documento": "01",
        "datos_del_cliente_o_receptor": {"codigo_tipo_documento_identidad": "6", "numero_documento": "20555555555"},
        **calc,
    })
    print(r["aceptado_por_sunat"], r["serie_numero"])
"""

from . import errores
from ._version import __version__
from .calculo import calcular_comprobante
from .cliente import OPERACIONES, Cliente, Transporte, hora_peru
from .errores import (
    ErrorDeAutenticacion,
    ErrorDeValidacion,
    FactuSmartError,
    LimiteDePeticiones,
    NoEncontrado,
    RucNoAutorizado,
    SinCreditos,
)

__all__ = [
    "__version__",
    "Cliente",
    "Transporte",
    "OPERACIONES",
    "calcular_comprobante",
    "hora_peru",
    "errores",
    "FactuSmartError",
    "ErrorDeAutenticacion",
    "SinCreditos",
    "RucNoAutorizado",
    "NoEncontrado",
    "ErrorDeValidacion",
    "LimiteDePeticiones",
]
