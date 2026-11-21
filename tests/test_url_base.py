"""Pruebas sin red: base_url opcional según el formato de la llave."""

import json
import unittest
from typing import Dict, List, Tuple

import factusmart

LLAVE_NUEVA = "fs_live_A0123456789B_" + "a1B2c3D4" * 4
LLAVE_NUEVA_TEST = "fs_test_AZYXWVTSRQPN_" + "Q" * 64
LLAVES_ANTIGUAS = [
    "k",
    "fs_test_" + "a" * 40,  # fs_test_ viejo, sin la cuenta
    "fs_live_AILOU0000000_" + "a" * 32,  # I, L, O, U no están en el alfabeto
    "fs_live_A0123456789B_" + "a" * 31,  # secreto corto
    "fs_live_A0123456789B_" + "a" * 32 + "-",
]


class TransporteFalso:
    def __init__(self) -> None:
        self.urls: List[str] = []

    def __call__(self, metodo, url, headers, cuerpo, timeout, contexto) -> Tuple[int, Dict[str, str], bytes]:
        self.urls.append(url)
        return 200, {}, json.dumps({"success": True}).encode("utf-8")


class TestUrlBase(unittest.TestCase):
    def test_reconoce_llaves_nuevas(self) -> None:
        self.assertTrue(factusmart.es_llave_nueva(LLAVE_NUEVA))
        self.assertTrue(factusmart.es_llave_nueva(LLAVE_NUEVA_TEST))
        for llave in LLAVES_ANTIGUAS:
            self.assertFalse(factusmart.es_llave_nueva(llave), llave)

    def test_llave_nueva_sin_base_url_usa_app(self) -> None:
        for kw in ({}, {"base_url": None}, {"base_url": "  "}):
            t = TransporteFalso()
            c = factusmart.Cliente(api_key=LLAVE_NUEVA, ruc="20100070970", transporte=t, **kw)  # type: ignore[arg-type]
            self.assertEqual(c.base_url, "https://app.factusmart.pe/api/v1/issuer")
            c.ping()
            self.assertEqual(t.urls[0], "https://app.factusmart.pe/api/v1/issuer/ping?ruc=20100070970")
        self.assertEqual(factusmart.URL_BASE_PREDETERMINADA, "https://app.factusmart.pe/api/v1/issuer")

    def test_llave_antigua_sin_base_url_lanza_error(self) -> None:
        for llave in LLAVES_ANTIGUAS:
            with self.assertRaisesRegex(ValueError, "Falta base_url: tu llave es del formato anterior"):
                factusmart.Cliente(api_key=llave)
        with self.assertRaisesRegex(ValueError, r"fs_live_…"):
            factusmart.Cliente(api_key="k", base_url="")

    def test_base_url_explicita_se_respeta(self) -> None:
        for llave in (LLAVE_NUEVA, "k"):
            t = TransporteFalso()
            c = factusmart.Cliente(api_key=llave, base_url="https://s2.factusmart.pe/api/v1/issuer/", transporte=t)
            self.assertEqual(c.base_url, "https://s2.factusmart.pe/api/v1/issuer")
            c.ping()
            self.assertTrue(t.urls[0].startswith("https://s2.factusmart.pe/api/v1/issuer/ping"))


if __name__ == "__main__":
    unittest.main()
