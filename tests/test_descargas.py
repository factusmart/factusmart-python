"""Descargas de guías (pdf/xml/cdr) y de anulaciones (xml/cdr), con transporte falso."""

import unittest

import factusmart
from factusmart import errores
from test_unitarios import cliente

BASE = "https://api.test/api/v1/issuer"
GUIA = "9f1c2d3e-4b5a-4c6d-8e7f-0123456789ab"


class TestDescargarGuia(unittest.TestCase):
    def test_descarga_pdf_xml_cdr(self) -> None:
        c, t, _ = cliente([(200, b"%PDF-1.4"), (200, b"<?xml"), (200, b"PK\x03\x04")])
        self.assertEqual(c.guias.descargar(GUIA, "PDF"), b"%PDF-1.4")
        self.assertEqual(c.guias.descargar(GUIA, "xml"), b"<?xml")
        self.assertEqual(c.guias.descargar(GUIA, "cdr", ruc="20609999991"), b"PK\x03\x04")
        self.assertEqual(
            [(p["metodo"], p["url"][len(BASE):]) for p in t.peticiones],
            [
                ("GET", "/guias/{}/pdf?ruc=20100070970".format(GUIA)),
                ("GET", "/guias/{}/xml?ruc=20100070970".format(GUIA)),
                ("GET", "/guias/{}/cdr?ruc=20609999991".format(GUIA)),
            ],
        )

    def test_404_json(self) -> None:
        cuerpo = {
            "success": False,
            "message": "El CDR de esta guía no está disponible todavía.",
            "codigo": "NO_ENCONTRADO",
            "reintentable": False,
        }
        c, t, _ = cliente([(404, cuerpo)])
        with self.assertRaises(errores.NoEncontrado) as ctx:
            c.guias.descargar(GUIA, "cdr")
        self.assertEqual(ctx.exception.codigo, factusmart.CodigoDeError.NO_ENCONTRADO)
        self.assertIs(ctx.exception.reintentable, False)
        self.assertEqual(len(t.peticiones), 1)

    def test_tipo_invalido(self) -> None:
        c, t, _ = cliente([])
        with self.assertRaises(ValueError):
            c.guias.descargar(GUIA, "zip")
        self.assertEqual(t.peticiones, [])


class TestDescargarAnulacion(unittest.TestCase):
    def test_descarga_xml_cdr(self) -> None:
        c, t, _ = cliente([(200, b"<?xml"), (200, b"PK\x03\x04")])
        self.assertEqual(c.anulaciones.descargar("tk/1", "XML"), b"<?xml")
        self.assertEqual(c.anulaciones.descargar("1712345678901", "cdr"), b"PK\x03\x04")
        self.assertEqual(
            [(p["metodo"], p["url"][len(BASE):]) for p in t.peticiones],
            [
                ("GET", "/anulaciones/tk%2F1/xml?ruc=20100070970"),
                ("GET", "/anulaciones/1712345678901/cdr?ruc=20100070970"),
            ],
        )

    def test_404_json(self) -> None:
        cuerpo = {"success": False, "message": "Anulación no encontrada.", "codigo": "NO_ENCONTRADO", "reintentable": False}
        c, t, _ = cliente([(404, cuerpo)])
        with self.assertRaises(errores.NoEncontrado) as ctx:
            c.anulaciones.descargar("1712345678901", "xml")
        self.assertEqual(ctx.exception.mensaje, "Anulación no encontrada.")
        self.assertEqual(ctx.exception.codigo, "NO_ENCONTRADO")
        self.assertEqual(len(t.peticiones), 1)

    def test_pdf_no_existe(self) -> None:
        c, t, _ = cliente([])
        with self.assertRaises(ValueError):
            c.anulaciones.descargar("1712345678901", "pdf")
        self.assertEqual(t.peticiones, [])


if __name__ == "__main__":
    unittest.main()
