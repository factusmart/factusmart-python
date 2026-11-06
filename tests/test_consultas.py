"""consultas.ruc / dni / documento (GET /consultas/{tipo}/{numero}), sin red."""

import unittest

import factusmart
from factusmart import errores
from test_unitarios import cliente

RUC_OK = {
    "success": True,
    "tipo": "ruc",
    "numero": "20131312955",
    "nombre": "SUPERINTENDENCIA NACIONAL DE ADUANAS Y DE ADMINISTRACION TRIBUTARIA - SUNAT",
    "direccion": "AV. GARCILASO DE LA VEGA - Nro: 1472  - LIMA",
    "estado": None,
    "condicion": None,
    "ubigeo": "150101",
    "desde_cache": False,
    "consultas_restantes": 29999,
    "periodo": "mes",
    "se_renueva": "2026-11-23",
}

DNI_OK = {
    "success": True,
    "tipo": "dni",
    "numero": "12345678",
    "nombre": "JUAN CARLOS PEREZ GARCIA",
    "direccion": None,
    "estado": None,
    "condicion": None,
    "ubigeo": None,
    "desde_cache": False,
    "consultas_restantes": 49,
    "periodo": "dia",
    "se_renueva": "2026-11-07",
}

LIMITE_CONSULTAS = {
    "consultas_restantes": 0,
    "limite_consultas": 50,
    "periodo": "dia",
    "se_renueva": "2026-11-07",
    "success": False,
    "message": "Llegaste al máximo de 50 consultas de DNI/RUC por día (cuenta sin plan).",
    "codigo": "LIMITE_CONSULTAS",
    "reintentable": False,
}

BASE = "https://api.test/api/v1/issuer"


class TestConsultas(unittest.TestCase):
    def test_ruc_get_sin_ruc_emisor_y_parseo(self) -> None:
        c, t, _ = cliente([(200, RUC_OK)])  # el cliente tiene ruc por defecto
        r = c.consultas.ruc("20131312955")
        p = t.peticiones[0]
        self.assertEqual(p["metodo"], "GET")
        self.assertEqual(p["url"], BASE + "/consultas/ruc/20131312955")
        self.assertNotIn("ruc=", p["url"])
        self.assertNotIn("X-RUC", {k.upper(): v for k, v in p["headers"].items()})
        self.assertIsNone(p["cuerpo"])
        self.assertEqual(r["nombre"], RUC_OK["nombre"])
        self.assertIsNone(r["estado"])
        self.assertEqual(r["ubigeo"], "150101")
        self.assertIs(r["desde_cache"], False)
        self.assertEqual(r["consultas_restantes"], 29999)
        self.assertEqual(r["periodo"], "mes")
        self.assertEqual(r["se_renueva"], "2026-11-23")

    def test_dni_y_documento_generico(self) -> None:
        c, t, _ = cliente([(200, DNI_OK), (200, DNI_OK)])
        self.assertEqual(c.consultas.dni("12345678")["nombre"], "JUAN CARLOS PEREZ GARCIA")
        r = c.consultas.documento(" DNI ", " 12345678 ")
        self.assertIsNone(r["direccion"])
        self.assertEqual(r["periodo"], "dia")
        for p in t.peticiones:
            self.assertEqual(p["url"], BASE + "/consultas/dni/12345678")

    def test_limite_consultas_no_se_reintenta(self) -> None:
        c, t, esperas = cliente([(429, LIMITE_CONSULTAS)] * 4, max_reintentos=3)
        with self.assertRaises(errores.LimiteDePeticiones) as ctx:
            c.consultas.ruc("20131312955")
        self.assertEqual(len(t.peticiones), 1)
        self.assertEqual(esperas, [])
        e = ctx.exception
        self.assertEqual(e.codigo, factusmart.CodigoDeError.LIMITE_CONSULTAS)
        self.assertIs(e.reintentable, False)
        self.assertEqual(e.respuesta["se_renueva"], "2026-11-07")

    def test_limite_peticiones_si_se_reintenta(self) -> None:
        limite = {"success": False, "message": "Demasiadas peticiones.", "codigo": "LIMITE_PETICIONES",
                  "reintentable": True, "retry_after": 2}
        c, t, esperas = cliente([(429, limite), (200, RUC_OK)])
        self.assertEqual(c.consultas.ruc("20131312955")["numero"], "20131312955")
        self.assertEqual(len(t.peticiones), 2)
        self.assertEqual(esperas, [2.0])

    def test_consulta_no_disponible_se_reintenta(self) -> None:
        caida = {"success": False, "message": "No se pudo consultar ahora.", "codigo": "CONSULTA_NO_DISPONIBLE",
                 "reintentable": True}
        c, t, _ = cliente([(503, caida), (503, caida), (200, RUC_OK)])
        c.consultas.ruc("20131312955")
        self.assertEqual(len(t.peticiones), 3)
        c, t, _ = cliente([(503, caida)] * 2, max_reintentos=1)
        with self.assertRaises(errores.FactuSmartError) as ctx:
            c.consultas.ruc("20131312955")
        self.assertEqual(ctx.exception.codigo, factusmart.CodigoDeError.CONSULTA_NO_DISPONIBLE)

    def test_no_encontrado_y_datos_invalidos_no_se_reintentan(self) -> None:
        nf = {"success": False, "message": "No se encontró el RUC en SUNAT.", "codigo": "NO_ENCONTRADO",
              "reintentable": False}
        c, t, _ = cliente([(404, nf)])
        with self.assertRaises(errores.NoEncontrado):
            c.consultas.ruc("20100070970")
        self.assertEqual(len(t.peticiones), 1)
        inv = {"campos": {"numero": ["El RUC no es válido."]}, "success": False,
               "message": "Datos inválidos: El RUC no es válido.", "codigo": "DATOS_INVALIDOS", "reintentable": False}
        c, t, _ = cliente([(422, inv)])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.consultas.ruc("20131312954")
        self.assertEqual(ctx.exception.campos, {"numero": ["El RUC no es válido."]})
        self.assertEqual(len(t.peticiones), 1)

    def test_contrato_mapeo(self) -> None:
        self.assertEqual(factusmart.OPERACIONES["lookupDocument"], "consultas.documento")
        self.assertEqual(factusmart.OPERACIONES["apiRoot"], "raiz")

    def test_raiz_get_sin_ruc(self) -> None:
        ok = {"success": True, "api": "FactuSmart API de facturación", "docs": "https://x/docs", "estado": "ok"}
        c, t, _ = cliente([(200, ok)])
        self.assertEqual(c.raiz()["estado"], "ok")
        p = t.peticiones[0]
        self.assertEqual(p["metodo"], "GET")
        self.assertEqual(p["url"], BASE + "/")


if __name__ == "__main__":
    unittest.main()
