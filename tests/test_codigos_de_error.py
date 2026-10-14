"""codigo / reintentable / campos de los errores y reintentos por "reintentable" (sin red)."""

import unittest
import urllib.error

import factusmart
from factusmart import errores
from test_unitarios import DATOS_BOLETA, EMISION_OK, cliente

ERROR_INTERNO = {"success": False, "message": "Error interno.", "codigo": "ERROR_INTERNO", "reintentable": True}
SUNAT_CAIDA = {"success": False, "message": "SUNAT no respondió.", "codigo": "SUNAT_NO_DISPONIBLE", "reintentable": True}


class TestCodigoReintentableCampos(unittest.TestCase):
    def test_lee_codigo_reintentable_y_campos(self) -> None:
        # Cuerpo real del API local (GET /documents?limite=500).
        cuerpo = {
            "limite": ["limite no debe ser mayor a 100."],
            "success": False,
            "message": "Datos inválidos: limite no debe ser mayor a 100.",
            "campos": {"limite": ["limite no debe ser mayor a 100."]},
            "codigo": "DATOS_INVALIDOS",
            "reintentable": False,
        }
        c, _, _ = cliente([(422, cuerpo)])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.comprobantes.listar({"limite": 500})
        e = ctx.exception
        self.assertEqual(e.codigo, factusmart.CodigoDeError.DATOS_INVALIDOS)
        self.assertIs(e.reintentable, False)
        self.assertEqual(e.campos, {"limite": ["limite no debe ser mayor a 100."]})
        self.assertEqual(e.mensaje, "Datos inválidos: limite no debe ser mayor a 100.")

    def test_servidor_viejo_sin_codigo(self) -> None:
        c, _, _ = cliente([(404, {"success": False, "message": "Comprobante no encontrado."})])
        with self.assertRaises(errores.NoEncontrado) as ctx:
            c.comprobantes.consultar("abc")
        self.assertIsNone(ctx.exception.codigo)
        self.assertIsNone(ctx.exception.reintentable)
        self.assertEqual(ctx.exception.campos, {})

    def test_cuerpo_no_json_y_error_de_red(self) -> None:
        c, _, _ = cliente([(500, "<html>boom</html>")], max_reintentos=0)
        with self.assertRaises(errores.FactuSmartError) as ctx:
            c.ping()
        self.assertIsNone(ctx.exception.codigo)
        self.assertIsNone(ctx.exception.reintentable)
        self.assertEqual(ctx.exception.campos, {})
        c, _, _ = cliente([urllib.error.URLError("sin red")], max_reintentos=0)
        with self.assertRaises(errores.FactuSmartError) as ctx:
            c.ping()
        self.assertIsNone(ctx.exception.codigo)
        self.assertIsNone(ctx.exception.reintentable)

    def test_tipos_raros_no_se_aceptan(self) -> None:
        c, _, _ = cliente([(422, {"message": "x", "codigo": 5, "reintentable": "true", "campos": ["a"]})])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.rucs.activar("20100070970", True)
        self.assertIsNone(ctx.exception.codigo)
        self.assertIsNone(ctx.exception.reintentable)
        self.assertEqual(ctx.exception.campos, {})

    def test_descarga_404_json(self) -> None:
        cuerpo = {"success": False, "message": "Comprobante no encontrado.", "codigo": "NO_ENCONTRADO", "reintentable": False}
        c, t, _ = cliente([(404, cuerpo)])
        with self.assertRaises(errores.NoEncontrado) as ctx:
            c.comprobantes.descargar("9f1c2d3e-4b5a-4c6d-8e7f-0123456789ab", "xml")
        self.assertEqual(ctx.exception.mensaje, "Comprobante no encontrado.")
        self.assertEqual(ctx.exception.codigo, "NO_ENCONTRADO")
        self.assertIs(ctx.exception.reintentable, False)
        self.assertEqual(len(t.peticiones), 1)

    def test_limite_lee_retry_after_del_cuerpo(self) -> None:
        cuerpo = {"success": False, "message": "Demasiadas peticiones.", "retry_after": 9, "codigo": "LIMITE_PETICIONES", "reintentable": True}
        c, _, esperas = cliente([(429, cuerpo), (200, {})])
        c.ping()
        self.assertEqual(esperas, [9.0])


class TestReintentableDelServidor(unittest.TestCase):
    def test_get_se_reintenta_con_500_reintentable(self) -> None:
        c, t, esperas = cliente([(500, ERROR_INTERNO), (200, {"success": True})])
        self.assertEqual(c.cuenta.saldo(), {"success": True})
        self.assertEqual(len(t.peticiones), 2)
        self.assertEqual(esperas, [1.0])

    def test_emitir_se_reintenta_con_la_misma_clave(self) -> None:
        c, t, _ = cliente([(422, SUNAT_CAIDA), (500, ERROR_INTERNO), (200, EMISION_OK)])
        c.comprobantes.emitir(DATOS_BOLETA)
        self.assertEqual(len(t.peticiones), 3)
        self.assertEqual(len({p["headers"]["Idempotency-Key"] for p in t.peticiones}), 1)

    def test_rucs_crear_se_reintenta(self) -> None:
        c, t, _ = cliente([(500, ERROR_INTERNO), (200, {"success": True})])
        c.rucs.crear({"ruc": "20609999991"})
        self.assertEqual(len(t.peticiones), 2)

    def test_reintentable_false_no_se_reintenta(self) -> None:
        cuerpo = {"success": False, "message": "x", "codigo": "ERROR_EMISION", "reintentable": False}
        c, t, _ = cliente([(422, cuerpo), (200, EMISION_OK)])
        with self.assertRaises(errores.ErrorDeValidacion):
            c.comprobantes.emitir(DATOS_BOLETA)
        self.assertEqual(len(t.peticiones), 1)

    def test_respeta_max_reintentos_y_backoff(self) -> None:
        c, t, esperas = cliente([(500, ERROR_INTERNO)] * 3, max_reintentos=2)
        with self.assertRaises(errores.FactuSmartError) as ctx:
            c.ping()
        self.assertEqual(len(t.peticiones), 3)
        self.assertEqual(esperas, [1.0, 2.0])
        self.assertEqual(ctx.exception.codigo, "ERROR_INTERNO")
        self.assertIs(ctx.exception.reintentable, True)

    def test_prohibidas_no_se_reintentan_aunque_el_servidor_lo_pida(self) -> None:
        llamadas = {
            "anulaciones.crear": lambda c: c.anulaciones.crear({"documentos": []}),
            "guias.emitir": lambda c: c.guias.emitir({"serie_documento": "TA01"}),
            "comprobantes.reenviar": lambda c: c.comprobantes.reenviar("abc"),
            "comprobantes.consultar_sunat": lambda c: c.comprobantes.consultar_sunat("abc"),
            "rucs.activar": lambda c: c.rucs.activar("20100070970", False),
        }
        for nombre, llamar in llamadas.items():
            for status, cuerpo in ((500, ERROR_INTERNO), (422, SUNAT_CAIDA)):
                with self.subTest(nombre, codigo=cuerpo["codigo"]):
                    c, t, esperas = cliente([(status, cuerpo), (200, {})])
                    with self.assertRaises(errores.FactuSmartError) as ctx:
                        llamar(c)
                    self.assertEqual(len(t.peticiones), 1)
                    self.assertEqual(esperas, [])
                    self.assertIs(ctx.exception.reintentable, True)


LIMITE_DIARIO = {
    "success": False,
    "message": "Llegaste al tope de 200 pruebas diarias de este RUC demo. Se reinicia a medianoche (hora de Lima).",
    "codigo": "LIMITE_PRUEBAS_DIARIO",
    "reintentable": False,
}


class TestReintentableFalseManda(unittest.TestCase):
    """5d: ``"reintentable": false`` en el cuerpo nunca se reintenta, sea cual sea el HTTP."""

    def test_429_limite_pruebas_diario_una_sola_peticion(self) -> None:
        c, t, esperas = cliente([(429, LIMITE_DIARIO, {"retry-after": "5"}), (200, EMISION_OK)])
        with self.assertRaises(errores.LimiteDePeticiones) as ctx:
            c.comprobantes.emitir(DATOS_BOLETA)
        e = ctx.exception
        self.assertIs(type(e), errores.LimiteDePeticiones)
        self.assertEqual(len(t.peticiones), 1)
        self.assertEqual(esperas, [])
        self.assertEqual(e.status, 429)
        self.assertEqual(e.codigo, factusmart.CodigoDeError.LIMITE_PRUEBAS_DIARIO)
        self.assertIs(e.reintentable, False)

    def test_429_limite_pruebas_diario_en_get_tampoco_se_reintenta(self) -> None:
        c, t, esperas = cliente([(429, LIMITE_DIARIO), (200, {"success": True})])
        with self.assertRaises(errores.LimiteDePeticiones):
            c.ping()
        self.assertEqual(len(t.peticiones), 1)
        self.assertEqual(esperas, [])

    def test_5xx_y_409_con_reintentable_false_no_se_reintentan(self) -> None:
        for status in (409, 500, 502, 503, 504):
            with self.subTest(status=status):
                cuerpo = {"success": False, "message": "x", "codigo": "CONFLICTO", "reintentable": False}
                c, t, esperas = cliente([(status, cuerpo), (200, EMISION_OK)])
                with self.assertRaises(errores.FactuSmartError) as ctx:
                    c.comprobantes.emitir(DATOS_BOLETA)
                self.assertEqual(len(t.peticiones), 1)
                self.assertEqual(esperas, [])
                self.assertIs(ctx.exception.reintentable, False)

    def test_429_reintentable_true_si_se_reintenta(self) -> None:
        cuerpo = {"success": False, "message": "Demasiadas peticiones.", "codigo": "LIMITE_PETICIONES", "reintentable": True}
        c, t, esperas = cliente([(429, cuerpo), (429, cuerpo), (200, {"success": True})])
        self.assertEqual(c.cuenta.saldo(), {"success": True})
        self.assertEqual(len(t.peticiones), 3)
        self.assertEqual(esperas, [1.0, 2.0])

    def test_429_sin_reintentable_usa_la_regla_por_http(self) -> None:
        c, t, _ = cliente([(429, {"success": False, "message": "Too Many Attempts."}), (200, {"success": True})])
        c.ping()
        self.assertEqual(len(t.peticiones), 2)

    def test_codigos_nuevos_en_catalogo(self) -> None:
        self.assertEqual(factusmart.CodigoDeError.ANULACION_MIXTA, "ANULACION_MIXTA")
        self.assertEqual(factusmart.CodigoDeError.LLAVE_DE_PRUEBA_EN_PRODUCCION, "LLAVE_DE_PRUEBA_EN_PRODUCCION")

    def test_anulacion_mixta_es_error_de_validacion(self) -> None:
        cuerpo = {"success": False, "message": "No mezcles facturas y boletas.", "codigo": "ANULACION_MIXTA", "reintentable": False}
        c, t, _ = cliente([(422, cuerpo)])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.anulaciones.crear({"documentos": []})
        self.assertEqual(ctx.exception.codigo, "ANULACION_MIXTA")
        self.assertEqual(len(t.peticiones), 1)


if __name__ == "__main__":
    unittest.main()
