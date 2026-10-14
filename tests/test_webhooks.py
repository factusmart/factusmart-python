"""Verificación de la firma de webhooks (sin red)."""

import hashlib
import hmac
import json
import unittest

import factusmart

# Vector común a los tres SDK (Node, PHP, Python).
CUERPO = '{"evento":"comprobante.aceptado"}'
SECRETO = "whsec_prueba"
FIRMA_ESPERADA = "bc1542f6420851152ae42abd2cbcfe8f651cba4a2822ddd07a15d0fe036f72da"


class TestVerificarFirmaWebhook(unittest.TestCase):
    def test_vector_comun(self) -> None:
        calculada = hmac.new(SECRETO.encode(), CUERPO.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(calculada, FIRMA_ESPERADA)
        self.assertIs(factusmart.verificar_firma_webhook(CUERPO, FIRMA_ESPERADA, SECRETO), True)

    def test_str_bytes_y_bytearray(self) -> None:
        for cuerpo in (CUERPO, CUERPO.encode("utf-8"), bytearray(CUERPO.encode("utf-8"))):
            for secreto in (SECRETO, SECRETO.encode("utf-8")):
                with self.subTest(cuerpo=type(cuerpo).__name__, secreto=type(secreto).__name__):
                    self.assertTrue(factusmart.verificar_firma_webhook(cuerpo, FIRMA_ESPERADA, secreto))

    def test_mayusculas_y_espacios(self) -> None:
        self.assertTrue(factusmart.verificar_firma_webhook(CUERPO, "  " + FIRMA_ESPERADA.upper() + "\n", SECRETO))

    def test_cuerpo_utf8(self) -> None:
        cuerpo = '{"cliente":"ÑANDÚ SAC"}'
        firma = hmac.new(b"s", cuerpo.encode("utf-8"), hashlib.sha256).hexdigest()
        self.assertTrue(factusmart.verificar_firma_webhook(cuerpo, firma, "s"))
        self.assertTrue(factusmart.verificar_firma_webhook(cuerpo.encode("utf-8"), firma, "s"))

    def test_cuerpo_alterado_o_secreto_equivocado(self) -> None:
        self.assertFalse(factusmart.verificar_firma_webhook('{"evento":"comprobante.rechazado"}', FIRMA_ESPERADA, SECRETO))
        self.assertFalse(factusmart.verificar_firma_webhook(CUERPO + " ", FIRMA_ESPERADA, SECRETO))
        self.assertFalse(factusmart.verificar_firma_webhook(CUERPO, FIRMA_ESPERADA, "whsec_otro"))

    def test_json_reserializado_no_verifica(self) -> None:
        reserializado = json.dumps(json.loads(CUERPO))  # agrega espacios: otros bytes
        self.assertFalse(factusmart.verificar_firma_webhook(reserializado, FIRMA_ESPERADA, SECRETO))

    def test_entradas_invalidas_dan_false_sin_lanzar(self) -> None:
        casos = [
            (CUERPO, "", SECRETO),
            (CUERPO, "   ", SECRETO),
            (CUERPO, None, SECRETO),
            (CUERPO, FIRMA_ESPERADA, ""),
            (CUERPO, FIRMA_ESPERADA, None),
            (None, FIRMA_ESPERADA, SECRETO),
            (123, FIRMA_ESPERADA, SECRETO),
            (CUERPO, 12345, SECRETO),
            (CUERPO, FIRMA_ESPERADA, 42),
            (CUERPO, "sha256=" + FIRMA_ESPERADA, SECRETO),
            (CUERPO, FIRMA_ESPERADA[:-1], SECRETO),
            (CUERPO, FIRMA_ESPERADA + "0", SECRETO),
            (CUERPO, "z" * 64, SECRETO),
            (CUERPO, b"\xff" * 64, SECRETO),
            (CUERPO, ["x"], SECRETO),
        ]
        for cuerpo, firma, secreto in casos:
            with self.subTest(firma=repr(firma)[:30], secreto=repr(secreto), cuerpo=repr(cuerpo)[:20]):
                self.assertIs(factusmart.verificar_firma_webhook(cuerpo, firma, secreto), False)

    def test_tambien_como_metodo_estatico_del_cliente(self) -> None:
        self.assertTrue(factusmart.Cliente.verificar_firma_webhook(CUERPO, FIRMA_ESPERADA, SECRETO))
        self.assertIn("verificar_firma_webhook", factusmart.__all__)
        self.assertEqual(factusmart.HEADER_FIRMA, "X-FactuSmart-Firma")


if __name__ == "__main__":
    unittest.main()
