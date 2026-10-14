"""Pruebas obligatorias 1-7 contra el API LOCAL (nunca contra producción).

Configuración por variables de entorno:

- ``FACTUSMART_TEST_BASE_URL`` (por defecto ``https://factusmart.test/api/v1/issuer``)
- ``FACTUSMART_TEST_API_KEY``  (por defecto ``test_apikey_demo_123``)
- ``FACTUSMART_TEST_RUC``      (por defecto ``20000000000``; si no pertenece a la
  cuenta se usa el primer RUC activo en modo demo de ``rucs.listar()``)
- ``FACTUSMART_INTEGRACION=0`` para saltarlas.

Gasta 2 créditos por corrida (boleta + prueba de idempotencia).
"""

import os
import unittest
import uuid

import factusmart
from factusmart import errores

BASE_URL = os.environ.get("FACTUSMART_TEST_BASE_URL", "https://factusmart.test/api/v1/issuer")
API_KEY = os.environ.get("FACTUSMART_TEST_API_KEY", "test_apikey_demo_123")
RUC = os.environ.get("FACTUSMART_TEST_RUC", "20000000000")

if "factusmart.pe" in BASE_URL:
    raise RuntimeError("Las pruebas de integración NO se corren contra producción.")

CLIENTE_DNI = {
    "codigo_tipo_documento_identidad": "1",
    "numero_documento": "12345678",
    "apellidos_y_nombres_o_razon_social": "CLIENTE PRUEBA SDK PYTHON",
}


def _boleta():
    calc = factusmart.calcular_comprobante(
        [{"codigo_interno": "SDK-PY-001", "descripcion": "Prueba SDK Python", "cantidad": 2, "valor_unitario": 10.5, "afectacion": "10"}]
    )
    return {"codigo_tipo_documento": "03", "datos_del_cliente_o_receptor": CLIENTE_DNI, "items": calc["items"], "totales": calc["totales"]}


@unittest.skipIf(os.environ.get("FACTUSMART_INTEGRACION") == "0", "FACTUSMART_INTEGRACION=0")
class TestIntegracion(unittest.TestCase):
    fs: factusmart.Cliente
    ruc: str
    emitido: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.fs = factusmart.Cliente(api_key=API_KEY, base_url=BASE_URL, ruc=RUC, verificar_ssl=False, max_reintentos=1)
        try:
            cls.fs.ping()
        except errores.RucNoAutorizado:
            activos = [r["ruc"] for r in cls.fs.rucs.listar()["rucs"] if r.get("activo") and r.get("entorno") == "demo"]
            if not activos:
                raise
            print("\n[aviso] El RUC {} no pertenece a la cuenta; se usa {}.".format(RUC, activos[0]))
            cls.fs.ruc = activos[0]
        except errores.FactuSmartError as e:
            if e.status is None:
                raise unittest.SkipTest("API local no disponible: {}".format(e))
            raise
        cls.ruc = cls.fs.ruc or ""

    def test_1_ping(self) -> None:
        r = self.fs.ping()
        self.assertTrue(r["success"])
        self.assertEqual(r["ruc_emisor"], self.ruc)
        self.assertIsInstance(r["creditos"], int)

    def test_2_saldo(self) -> None:
        r = self.fs.cuenta.saldo()
        self.assertIn("creditos_disponibles", r)
        self.assertIsInstance(r["creditos_disponibles"], int)

    def test_3_emitir_boleta(self) -> None:
        r = self.fs.comprobantes.emitir(_boleta())
        TestIntegracion.emitido = r
        self.assertTrue(r["success"])
        self.assertTrue(r["aceptado_por_sunat"], r.get("sunat"))
        self.assertEqual(r["entorno"], "prueba")
        self.assertTrue(r["serie_numero"].startswith("B"))

    def test_4_consultar_historial_descargar(self) -> None:
        if not self.emitido:
            self.skipTest("Depende de test_3")
        eid = self.emitido["external_id"]
        c = self.fs.comprobantes.consultar(eid)
        self.assertEqual(c["external_id"], eid)
        self.assertEqual(c["serie_numero"], self.emitido["serie_numero"])
        self.assertIn("pdf", c["links"])
        h = self.fs.comprobantes.historial(eid)
        self.assertEqual(h["external_id"], eid)
        self.assertGreaterEqual(len(h["historial"]), 1)
        pdf = self.fs.comprobantes.descargar(eid, "pdf")
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b"%PDF"), pdf[:20])

    def test_5_idempotencia(self) -> None:
        clave = "sdk-python-" + str(uuid.uuid4())
        antes = self.fs.cuenta.saldo()["creditos_disponibles"]
        r1 = self.fs.comprobantes.emitir(_boleta(), idempotency_key=clave)
        r2 = self.fs.comprobantes.emitir(_boleta(), idempotency_key=clave)
        despues = self.fs.cuenta.saldo()["creditos_disponibles"]
        self.assertEqual(r1["external_id"], r2["external_id"])
        self.assertEqual(r1["serie_numero"], r2["serie_numero"])
        self.assertEqual(antes - despues, 1, "el saldo debe bajar solo 1 (antes={}, después={})".format(antes, despues))

    def test_6_api_key_falsa(self) -> None:
        falso = factusmart.Cliente(api_key="clave_que_no_existe", base_url=BASE_URL, ruc=self.ruc, verificar_ssl=False)
        with self.assertRaises(errores.ErrorDeAutenticacion) as ctx:
            falso.ping()
        self.assertEqual(ctx.exception.status, 401)
        self.assertTrue(ctx.exception.mensaje)

    def test_7_payload_invalido(self) -> None:
        datos = dict(_boleta(), serie_documento="ZZ99")
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            self.fs.comprobantes.emitir(datos)
        self.assertEqual(ctx.exception.status, 422)
        self.assertIn("ZZ99", ctx.exception.mensaje)
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            self.fs.comprobantes.listar({"limite": 500})
        self.assertIn("limite", ctx.exception.mensaje)


if __name__ == "__main__":
    unittest.main()
