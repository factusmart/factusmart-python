"""Prueba 8 (contrato): cada operationId de openapi.yaml debe tener su método en el SDK.

Lee el archivo oficial sin dependencias (regex sobre ``operationId:``). Si el
API crece y el SDK no, esta prueba falla.

Ruta del archivo: variable de entorno ``FACTUSMART_OPENAPI`` o, por defecto,
``tests/fixtures/openapi.yaml`` (copia del archivo oficial).
"""

import os
import re
import unittest

import factusmart

RUTA_OPENAPI = os.environ.get("FACTUSMART_OPENAPI", os.path.join(os.path.dirname(__file__), "fixtures", "openapi.yaml"))


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

    def test_herramientas_mapeadas(self) -> None:
        ids = set(operation_ids(RUTA_OPENAPI))
        esperado = {
            "calculateDocument": "comprobantes.calcular",
            "listCatalogs": "catalogos.listar",
            "getCatalog": "catalogos.consultar",
            "listEstablishments": "establecimientos.listar",
            "createEstablishment": "establecimientos.crear",
            "searchSunatProductCodes": "catalogos.buscar_producto_sunat",
        }
        for op, metodo in esperado.items():
            with self.subTest(op):
                self.assertIn(op, ids)
                self.assertEqual(factusmart.OPERACIONES.get(op), metodo)

    def test_no_sobran_operaciones(self) -> None:
        ids = set(operation_ids(RUTA_OPENAPI))
        sobran = set(factusmart.OPERACIONES) - ids
        self.assertEqual(sobran, set(), "El SDK mapea operaciones que ya no están en openapi.yaml")

    def test_cada_codigo_de_error_tiene_constante(self) -> None:
        with open(RUTA_OPENAPI, encoding="utf-8") as f:
            texto = f.read()
        m = re.search(r"^    CodigoError:\r?\n(.*?)\r?\n    [A-Za-z]+:\r?\n", texto, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(m, "falta CodigoError en openapi.yaml")
        valores = re.findall(r"^\s+- ([A-Z_]+)\s*$", m.group(1), re.MULTILINE)
        self.assertGreater(len(valores), 0)
        for codigo in valores:
            self.assertEqual(getattr(factusmart.CodigoDeError, codigo, None), codigo, "Falta CodigoDeError." + codigo)


if __name__ == "__main__":
    unittest.main()
