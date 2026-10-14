"""Prueba 8 (contrato): cada operationId de openapi.yaml debe tener su método en el SDK.

Lee el archivo oficial sin dependencias (regex sobre ``operationId:``). Si el
API crece y el SDK no, esta prueba falla.

Ruta del archivo: variable de entorno ``FACTUSMART_OPENAPI`` o, por defecto,
``C:\\laragon\\www\\factusmart\\docs\\api\\openapi.yaml``.
"""

import os
import re
import unittest

import factusmart

RUTA_OPENAPI = os.environ.get("FACTUSMART_OPENAPI", r"C:\laragon\www\factusmart\docs\api\openapi.yaml")


def operation_ids(ruta: str):
    with open(ruta, encoding="utf-8") as f:
        return re.findall(r"^\s*operationId:\s*['\"]?([A-Za-z0-9_]+)", f.read(), re.MULTILINE)


class TestContrato(unittest.TestCase):
    def setUp(self) -> None:
        if not os.path.isfile(RUTA_OPENAPI):
            self.skipTest("No se encontró openapi.yaml en {} (define FACTUSMART_OPENAPI).".format(RUTA_OPENAPI))

    def test_cada_operation_id_tiene_metodo(self) -> None:
        ids = operation_ids(RUTA_OPENAPI)
        self.assertGreaterEqual(len(ids), 1)
        fs = factusmart.Cliente(api_key="x", base_url="https://x")
        faltan = []
        for op in ids:
            ruta = factusmart.OPERACIONES.get(op)
            if not ruta:
                faltan.append("{} (sin entrada en OPERACIONES)".format(op))
                continue
            obj = fs
            for parte in ruta.split("."):
                obj = getattr(obj, parte, None)
            if not callable(obj):
                faltan.append("{} -> {} (no existe)".format(op, ruta))
        self.assertEqual(faltan, [], "operationId sin método en el SDK: {}".format(faltan))

    def test_no_sobran_operaciones(self) -> None:
        ids = set(operation_ids(RUTA_OPENAPI))
        sobran = set(factusmart.OPERACIONES) - ids
        self.assertEqual(sobran, set(), "El SDK mapea operaciones que ya no están en openapi.yaml")


if __name__ == "__main__":
    unittest.main()
