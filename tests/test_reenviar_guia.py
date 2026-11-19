"""Reenvío de guías a SUNAT (POST /guias/{id}/reenviar) y código NOTA_EXCEDE_COMPROBANTE, con transporte falso."""

import unittest

import factusmart
from factusmart import errores
from test_unitarios import cliente

BASE = "https://api.test/api/v1/issuer"
GUIA = "9f1c2d3e-4b5a-4c6d-8e7f-0123456789ab"

REENVIO_OK = {
    "success": True,
    "serie_numero": "T001-15",
    "external_id": GUIA,
    "enviado": True,
    "estado": "03",
    "mensaje": "Guía enviada a SUNAT.",
    "links": {"xml": "https://api.test/x.xml", "pdf": "https://api.test/x.pdf", "cdr": None},
    "envio": {"ticket": "abc-123"},
    "creditos_consumidos": 1,
    "creditos_restantes": 99,
}


class TestReenviarGuia(unittest.TestCase):
    def test_reenvio_ok(self) -> None:
        c, t, _ = cliente([(200, REENVIO_OK), (200, REENVIO_OK)])
        r = c.guias.reenviar(GUIA)
        self.assertIs(r["enviado"], True)
        self.assertEqual(r["serie_numero"], "T001-15")
        self.assertEqual(r["links"]["pdf"], "https://api.test/x.pdf")
        c.guias.reenviar("a/b", ruc="20609999991")
        self.assertEqual(
            [(p["metodo"], p["url"][len(BASE):], p["cuerpo"]) for p in t.peticiones],
            [
                ("POST", "/guias/{}/reenviar".format(GUIA), {"ruc": "20100070970"}),
                ("POST", "/guias/a%2Fb/reenviar", {"ruc": "20609999991"}),
            ],
        )

    def test_envio_fallido_422(self) -> None:
        cuerpo = {
            "success": False,
            "message": "SUNAT no respondió al reenvío.",
            "codigo": "REENVIO_FALLIDO",
            "reintentable": True,
        }
        c, t, _ = cliente([(422, cuerpo)])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.guias.reenviar(GUIA)
        self.assertEqual(ctx.exception.codigo, factusmart.CodigoDeError.REENVIO_FALLIDO)
        self.assertIs(ctx.exception.reintentable, True)
        self.assertEqual(ctx.exception.mensaje, "SUNAT no respondió al reenvío.")
        self.assertEqual(len(t.peticiones), 1)  # nunca se reintenta solo

    def test_guia_no_registrada_422(self) -> None:
        cuerpo = {
            "success": False,
            "message": "La guía no está en estado Registrado (01).",
            "codigo": "REENVIO_FALLIDO",
            "estado": "05",
        }
        c, t, _ = cliente([(422, cuerpo)])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.guias.reenviar(GUIA)
        self.assertEqual(ctx.exception.codigo, "REENVIO_FALLIDO")
        self.assertEqual(ctx.exception.respuesta["estado"], "05")
        self.assertEqual(len(t.peticiones), 1)

    def test_404(self) -> None:
        cuerpo = {"success": False, "message": "Guía no encontrada.", "codigo": "NO_ENCONTRADO", "reintentable": False}
        c, t, _ = cliente([(404, cuerpo)])
        with self.assertRaises(errores.NoEncontrado) as ctx:
            c.guias.reenviar(GUIA)
        self.assertEqual(ctx.exception.codigo, factusmart.CodigoDeError.NO_ENCONTRADO)
        self.assertEqual(len(t.peticiones), 1)

    def test_operacion_mapeada(self) -> None:
        self.assertEqual(factusmart.OPERACIONES["resendDispatchGuide"], "guias.reenviar")


class TestNotaExcedeComprobante(unittest.TestCase):
    def test_codigo_nuevo(self) -> None:
        self.assertEqual(factusmart.CodigoDeError.NOTA_EXCEDE_COMPROBANTE, "NOTA_EXCEDE_COMPROBANTE")
        cuerpo = {
            "success": False,
            "message": "La nota de crédito excede el comprobante afectado: quedan S/ 20.00 disponibles.",
            "codigo": "NOTA_EXCEDE_COMPROBANTE",
            "reintentable": False,
        }
        c, t, _ = cliente([(422, cuerpo)])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.comprobantes.emitir(
                {
                    "codigo_tipo_documento": "07",
                    "datos_del_cliente_o_receptor": {"codigo_tipo_documento_identidad": "6", "numero_documento": "20100070970"},
                    "items": [{"descripcion": "X", "cantidad": 1}],
                    "totales": {"total_venta": 100},
                }
            )
        self.assertEqual(ctx.exception.codigo, factusmart.CodigoDeError.NOTA_EXCEDE_COMPROBANTE)
        self.assertIs(ctx.exception.reintentable, False)
        self.assertEqual(len(t.peticiones), 1)


if __name__ == "__main__":
    unittest.main()
