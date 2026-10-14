"""Pruebas obligatorias 1-8 (incluidas 5b y 5c), 10 y 11 contra el API LOCAL (nunca contra producción).

Configuración por variables de entorno:

- ``FACTUSMART_TEST_BASE_URL`` (por defecto ``https://factusmart.test/api/v1/issuer``)
- ``FACTUSMART_TEST_API_KEY``  (por defecto ``test_apikey_demo_123``)
- ``FACTUSMART_TEST_RUC``      (por defecto ``20777666555``; si no pertenece a la
  cuenta se usa el primer RUC activo en modo demo de ``rucs.listar()``)
- ``FACTUSMART_INTEGRACION=0`` para saltarlas.

En RUC demo no se cobra crédito, pero hay un tope de 200 operaciones/día por
cuenta (compartido con los otros SDK). Esta suite hace solo 2 emisiones nuevas
por corrida: la boleta de la prueba 3 (que la prueba 5 reusa para la
idempotencia) y la boleta armada con ``comprobantes.calcular`` (prueba 5b).
"""

import json
import os
import unittest
import uuid

import factusmart
from factusmart import errores

BASE_URL = os.environ.get("FACTUSMART_TEST_BASE_URL", "https://factusmart.test/api/v1/issuer")
API_KEY = os.environ.get("FACTUSMART_TEST_API_KEY", "test_apikey_demo_123")
RUC = os.environ.get("FACTUSMART_TEST_RUC", "20777666555")
RESULTADO_CASO_COMUN = os.path.join(os.path.dirname(__file__), os.pardir, "resultado_caso_comun.json")
CASO_COMUN = [
    {"descripcion": "A", "cantidad": 3, "valor_unitario": 10.555, "afectacion": "10"},
    {"descripcion": "B", "cantidad": 2, "valor_unitario": 5, "afectacion": "20"},
    {"descripcion": "C", "cantidad": 1, "valor_unitario": 7.1, "afectacion": "30"},
    {"descripcion": "D", "cantidad": 1, "valor_unitario": 100, "afectacion": "40"},
]

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
    clave_emitido: str = ""

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
        clave = "sdk-python-" + str(uuid.uuid4())
        r = self.fs.comprobantes.emitir(_boleta(), idempotency_key=clave)
        TestIntegracion.emitido = r
        TestIntegracion.clave_emitido = clave
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
        # Reusa la clave de la prueba 3 para no gastar otra emisión del tope diario.
        if self.emitido and self.clave_emitido:
            clave, r1 = self.clave_emitido, self.emitido
        else:
            clave = "sdk-python-" + str(uuid.uuid4())
            r1 = self.fs.comprobantes.emitir(_boleta(), idempotency_key=clave)
        r2 = self.fs.comprobantes.emitir(_boleta(), idempotency_key=clave)
        self.assertEqual(r1["external_id"], r2["external_id"])
        self.assertEqual(r1["serie_numero"], r2["serie_numero"])
        # En demo no se cobra nada: no se mira el saldo, solo que la repetición no cobre.
        if "credito_cobrado" in r2:
            self.assertIs(r2["credito_cobrado"], False, r2)

    def test_5b_calcular_en_servidor_y_emitir(self) -> None:
        with open(RESULTADO_CASO_COMUN, encoding="utf-8") as f:
            esperado = json.load(f)
        r = self.fs.comprobantes.calcular(CASO_COMUN)
        self.assertTrue(r["success"])
        self.assertEqual(r["items"], esperado["items"])
        self.assertEqual(r["totales"], esperado["totales"])
        # La exportación (40) no va en boleta: se emite una boleta con precio con IGV.
        calc = self.fs.comprobantes.calcular(
            [{"codigo_interno": "SDK-PY-002", "descripcion": "Menu SDK Python", "cantidad": 3, "precio_unitario": 10, "afectacion": "10", "unidad_de_medida": "ZZ"}]
        )
        self.assertEqual(calc["totales"]["total_venta"], 30)
        e = self.fs.comprobantes.emitir(
            {"codigo_tipo_documento": "03", "datos_del_cliente_o_receptor": CLIENTE_DNI, "items": calc["items"], "totales": calc["totales"]}
        )
        self.assertTrue(e["aceptado_por_sunat"], e.get("sunat"))
        self.assertEqual(e["entorno"], "prueba")

    def test_5c_catalogos(self) -> None:
        lista = self.fs.catalogos.listar()
        self.assertIsInstance(lista["catalogos"], list)
        self.assertGreater(len(lista["catalogos"]), 0)
        afectacion = self.fs.catalogos.consultar("07")
        codigos = [fila.get("codigo") for fila in afectacion["datos"]]
        self.assertIn("10", codigos)
        filtrado = self.fs.catalogos.consultar("unidades", q="kilo")
        self.assertTrue(all("codigo" in fila for fila in filtrado["datos"]))

    def test_6_api_key_falsa(self) -> None:
        falso = factusmart.Cliente(api_key="clave_que_no_existe", base_url=BASE_URL, ruc=self.ruc, verificar_ssl=False)
        with self.assertRaises(errores.ErrorDeAutenticacion) as ctx:
            falso.ping()
        self.assertEqual(ctx.exception.status, 401)
        self.assertTrue(ctx.exception.mensaje)
        self.assertEqual(ctx.exception.codigo, "NO_AUTENTICADO")
        self.assertIs(ctx.exception.reintentable, False)

    def test_7_payload_invalido(self) -> None:
        datos = dict(_boleta(), serie_documento="ZZ99")
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            self.fs.comprobantes.emitir(datos)
        self.assertEqual(ctx.exception.status, 422)
        self.assertIn("ZZ99", ctx.exception.mensaje)
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            self.fs.comprobantes.listar({"limite": 500})
        self.assertIn("limite", ctx.exception.mensaje)
        self.assertEqual(ctx.exception.codigo, "DATOS_INVALIDOS")
        self.assertIs(ctx.exception.reintentable, False)
        self.assertIn("limite", ctx.exception.campos)

    def test_8_descarga_inexistente_es_404_json(self) -> None:
        inexistente = str(uuid.uuid4())
        with self.assertRaises(errores.NoEncontrado) as ctx:
            self.fs.comprobantes.descargar(inexistente, "pdf")
        e = ctx.exception
        self.assertEqual(e.status, 404)
        self.assertEqual(e.codigo, "NO_ENCONTRADO", e.respuesta)
        self.assertIs(e.reintentable, False)
        self.assertIsInstance(e.respuesta, dict)
        self.assertEqual(e.mensaje, e.respuesta.get("message"))



@unittest.skipIf(os.environ.get("FACTUSMART_INTEGRACION") == "0", "FACTUSMART_INTEGRACION=0")
class TestIntegracionSinEmitir(unittest.TestCase):
    """Pruebas 10 y 11: anexos y PDF por ``formato``. NO emiten ni crean nada.

    Se apagan con ``FACTUSMART_INTEGRACION=0`` como el resto. Solas (sin
    emitir nada, aunque la variable no esté definida)::

        python -m unittest tests.test_integracion.TestIntegracionSinEmitir

    ``establecimientos.crear`` solo se prueba sin red (el plan demo limita los locales).
    """

    fs: factusmart.Cliente

    @classmethod
    def setUpClass(cls) -> None:
        cls.fs = factusmart.Cliente(api_key=API_KEY, base_url=BASE_URL, ruc=RUC, verificar_ssl=False, max_reintentos=1)
        try:
            cls.fs.ping()
        except errores.FactuSmartError as e:
            if e.status is None:
                raise unittest.SkipTest("API local no disponible: {}".format(e))
            raise

    def test_10_establecimientos_listar(self) -> None:
        r = self.fs.establecimientos.listar()
        self.assertTrue(r["success"])
        self.assertIsInstance(r["establecimientos"], list)
        self.assertGreaterEqual(len(r["establecimientos"]), 1)
        local = r["establecimientos"][0]
        for campo in ("codigo_anexo", "nombre", "predeterminado", "series"):
            self.assertIn(campo, local)

    def test_11_pdf_ticket58_de_un_comprobante_existente(self) -> None:
        lista = self.fs.comprobantes.listar({"limite": 1})
        docs = lista.get("comprobantes") or []
        if not docs:
            self.skipTest("El RUC no tiene comprobantes para descargar: {}".format(sorted(lista)))
        external_id = docs[0]["external_id"]
        pdf = self.fs.comprobantes.descargar(external_id, "pdf", formato="ticket58")
        self.assertIsInstance(pdf, bytes)
        self.assertTrue(pdf.startswith(b"%PDF"), pdf[:40])
        a4 = self.fs.comprobantes.descargar(external_id, "pdf")
        self.assertTrue(a4.startswith(b"%PDF"))
        self.assertNotEqual(pdf, a4)

    def test_12_buscar_producto_sunat(self) -> None:
        r = self.fs.catalogos.buscar_producto_sunat("computador", limite=10)
        self.assertTrue(r["success"])
        self.assertEqual(r["catalogo_sunat"], "25")
        self.assertLessEqual(len(r["datos"]), 10)
        self.assertIn("43211503", [fila.get("codigo") for fila in r["datos"]], r)


if __name__ == "__main__":
    unittest.main()
