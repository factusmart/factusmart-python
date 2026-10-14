"""Pruebas sin red: transporte falso inyectado en el Cliente."""

import json
import re
import unittest
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import factusmart
from factusmart import errores

UUID_V4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


class TransporteFalso:
    """Devuelve respuestas programadas y guarda cada petición."""

    def __init__(self, respuestas: List[Any]) -> None:
        self.respuestas = list(respuestas)
        self.peticiones: List[Dict[str, Any]] = []

    def __call__(self, metodo, url, headers, cuerpo, timeout, contexto) -> Tuple[int, Dict[str, str], bytes]:
        self.peticiones.append(
            {
                "metodo": metodo,
                "url": url,
                "headers": headers,
                "cuerpo": json.loads(cuerpo.decode("utf-8")) if cuerpo else None,
            }
        )
        r = self.respuestas.pop(0)
        if isinstance(r, BaseException):
            raise r
        status, cuerpo_resp = r[0], r[1]
        cabeceras = r[2] if len(r) > 2 else {}
        if isinstance(cuerpo_resp, (dict, list)):
            cuerpo_resp = json.dumps(cuerpo_resp).encode("utf-8")
        elif isinstance(cuerpo_resp, str):
            cuerpo_resp = cuerpo_resp.encode("utf-8")
        return status, cabeceras, cuerpo_resp


EMISION_OK = {
    "success": True,
    "estado": "05",
    "serie_numero": "BA01-1",
    "external_id": "9822f52c-108e-47ff-9d2e-5f0c3c1a7b11",
    "creditos_restantes": 10,
    "aceptado_por_sunat": True,
    "entorno": "prueba",
    "tiene_validez_fiscal": False,
}

DATOS_BOLETA = {
    "codigo_tipo_documento": "03",
    "datos_del_cliente_o_receptor": {"codigo_tipo_documento_identidad": "1", "numero_documento": "77344962"},
    "items": [{"descripcion": "X", "cantidad": 1}],
    "totales": {"total_venta": 1},
}


def cliente(respuestas: List[Any], **kw: Any) -> Tuple[factusmart.Cliente, TransporteFalso, List[float]]:
    t = TransporteFalso(respuestas)
    esperas: List[float] = []
    opciones: Dict[str, Any] = dict(api_key="k", base_url="https://api.test/api/v1/issuer/", ruc="20123456789")
    opciones.update(kw)
    c = factusmart.Cliente(transporte=t, dormir=esperas.append, **opciones)
    return c, t, esperas


class TestConstructor(unittest.TestCase):
    def test_falta_api_key_o_base_url(self) -> None:
        with self.assertRaisesRegex(ValueError, "api_key"):
            factusmart.Cliente(api_key="", base_url="https://x")
        with self.assertRaisesRegex(ValueError, "base_url"):
            factusmart.Cliente(api_key="k", base_url="")

    def test_quita_barra_final_y_manda_api_key(self) -> None:
        c, t, _ = cliente([(200, {"success": True})])
        c.ping()
        self.assertEqual(t.peticiones[0]["url"], "https://api.test/api/v1/issuer/ping?ruc=20123456789")
        self.assertEqual(t.peticiones[0]["headers"]["X-API-Key"], "k")
        self.assertEqual(t.peticiones[0]["headers"]["Accept"], "application/json")


class TestIdempotencia(unittest.TestCase):
    def test_reintento_de_emitir_reusa_la_misma_clave(self) -> None:
        c, t, esperas = cliente(
            [
                urllib.error.URLError("conexión reiniciada"),
                (503, {"success": False, "message": "Service Unavailable"}),
                (409, {"success": False, "message": "Ya hay una emisión en curso con esa Idempotency-Key."}),
                (200, EMISION_OK),
            ]
        )
        r = c.comprobantes.emitir(DATOS_BOLETA)
        self.assertEqual(r["external_id"], EMISION_OK["external_id"])
        claves = {p["headers"]["Idempotency-Key"] for p in t.peticiones}
        self.assertEqual(len(t.peticiones), 4)
        self.assertEqual(len(claves), 1, "todas las peticiones deben llevar la MISMA Idempotency-Key")
        self.assertRegex(claves.pop(), UUID_V4)
        self.assertEqual(esperas, [1.0, 2.0, 4.0])

    def test_clave_del_usuario_se_respeta(self) -> None:
        c, t, _ = cliente([(502, ""), (200, EMISION_OK)])
        c.comprobantes.emitir(DATOS_BOLETA, idempotency_key="venta-123")
        self.assertEqual([p["headers"]["Idempotency-Key"] for p in t.peticiones], ["venta-123", "venta-123"])

    def test_dos_llamadas_distintas_usan_claves_distintas(self) -> None:
        c, t, _ = cliente([(200, EMISION_OK), (200, EMISION_OK)])
        c.comprobantes.emitir(DATOS_BOLETA)
        c.comprobantes.emitir(DATOS_BOLETA)
        self.assertNotEqual(t.peticiones[0]["headers"]["Idempotency-Key"], t.peticiones[1]["headers"]["Idempotency-Key"])

    def test_se_agotan_los_reintentos(self) -> None:
        c, t, esperas = cliente([(503, "")] * 4)
        with self.assertRaises(factusmart.FactuSmartError) as ctx:
            c.comprobantes.emitir(DATOS_BOLETA)
        self.assertEqual(ctx.exception.status, 503)
        self.assertEqual(len(t.peticiones), 4)  # 1 + max_reintentos (3)


class TestReglaDeOro(unittest.TestCase):
    def test_200_no_aceptado_no_lanza(self) -> None:
        rechazo = dict(EMISION_OK, estado="01", aceptado_por_sunat=False, sunat={"codigo": "0306", "descripcion": "x"})
        c, _, _ = cliente([(200, rechazo)])
        r = c.comprobantes.emitir(DATOS_BOLETA)
        self.assertFalse(r["aceptado_por_sunat"])
        self.assertEqual(r["estado"], "01")


class TestErrores(unittest.TestCase):
    def test_mapeo_http_a_excepcion(self) -> None:
        casos = {
            401: errores.ErrorDeAutenticacion,
            402: errores.SinCreditos,
            403: errores.RucNoAutorizado,
            404: errores.NoEncontrado,
            422: errores.ErrorDeValidacion,
            429: errores.LimiteDePeticiones,
            400: errores.FactuSmartError,
            500: errores.FactuSmartError,
        }
        for status, clase in casos.items():
            with self.subTest(status=status):
                cuerpo = {"success": False, "message": "mensaje {}".format(status)}
                c, _, _ = cliente([(status, cuerpo)], max_reintentos=0)
                with self.assertRaises(clase) as ctx:
                    c.cuenta.saldo()
                self.assertIs(type(ctx.exception), clase)
                self.assertIsInstance(ctx.exception, errores.FactuSmartError)
                self.assertEqual(ctx.exception.status, status)
                self.assertEqual(ctx.exception.mensaje, "mensaje {}".format(status))
                self.assertEqual(ctx.exception.respuesta, cuerpo)

    def test_500_too_many_attempts_es_limite(self) -> None:
        c, _, _ = cliente([(500, {"success": False, "message": "Too Many Attempts.", "line": 200})], max_reintentos=0)
        with self.assertRaises(errores.LimiteDePeticiones):
            c.ping()

    def test_422_con_mapa_de_laravel_da_mensaje_legible(self) -> None:
        c, _, _ = cliente([(422, {"limite": ["El campo limite no debe ser mayor que 100."]})])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.comprobantes.listar({"limite": 500})
        self.assertEqual(ctx.exception.mensaje, "limite: El campo limite no debe ser mayor que 100.")

    def test_404_html_de_descarga(self) -> None:
        c, _, _ = cliente([(404, "<html>no existe</html>")])
        with self.assertRaises(errores.NoEncontrado) as ctx:
            c.comprobantes.descargar("abc", "pdf")
        self.assertEqual(ctx.exception.respuesta, "<html>no existe</html>")

    def test_error_de_red_sin_reintentos_es_factusmart_error(self) -> None:
        c, _, _ = cliente([urllib.error.URLError("sin red")], max_reintentos=0)
        with self.assertRaises(errores.FactuSmartError) as ctx:
            c.ping()
        self.assertIsNone(ctx.exception.status)
        self.assertIn("sin red", ctx.exception.mensaje)


class TestLimiteDePeticiones(unittest.TestCase):
    def test_429_respeta_retry_after(self) -> None:
        c, t, esperas = cliente([(429, {"success": False, "message": "Too Many"}, {"Retry-After": "7"}), (200, {"ok": 1})])
        self.assertEqual(c.cuenta.saldo(), {"ok": 1})
        self.assertEqual(esperas, [7.0])
        self.assertEqual(len(t.peticiones), 2)

    def test_429_lee_espera_n_segundos_del_mensaje(self) -> None:
        c, _, esperas = cliente([(429, {"success": False, "message": "Límite alcanzado. Espera 5 segundos."}), (200, {})])
        c.ping()
        self.assertEqual(esperas, [5.0])

    def test_429_sin_datos_usa_espera_creciente(self) -> None:
        c, _, esperas = cliente([(429, {}), (429, {}), (200, {})])
        c.ping()
        self.assertEqual(esperas, [1.0, 2.0])

    def test_limite_agotado_trae_segundos_de_espera(self) -> None:
        c, _, _ = cliente([(429, {"message": "x"}, {"retry-after": "3"})], max_reintentos=0)
        with self.assertRaises(errores.LimiteDePeticiones) as ctx:
            c.ping()
        self.assertEqual(ctx.exception.segundos_de_espera, 3.0)


class TestNoReintentar(unittest.TestCase):
    def test_operaciones_que_nunca_se_reintentan(self) -> None:
        llamadas = {
            "anulaciones.crear": lambda c: c.anulaciones.crear({"documentos": []}),
            "guias.emitir": lambda c: c.guias.emitir({"serie_documento": "TA01"}),
            "comprobantes.reenviar": lambda c: c.comprobantes.reenviar("abc"),
            "comprobantes.consultar_sunat": lambda c: c.comprobantes.consultar_sunat("abc"),
            "rucs.activar": lambda c: c.rucs.activar("20123456789", False),
        }
        for nombre, llamar in llamadas.items():
            with self.subTest(nombre):
                c, t, esperas = cliente([(503, ""), (200, {})])
                with self.assertRaises(errores.FactuSmartError):
                    llamar(c)
                self.assertEqual(len(t.peticiones), 1)
                self.assertEqual(esperas, [])

    def test_409_solo_se_reintenta_en_emitir(self) -> None:
        c, t, _ = cliente([(409, {"success": False, "message": "otra cuenta"}), (200, {})])
        with self.assertRaises(errores.FactuSmartError):
            c.rucs.crear({"ruc": "20609999991"})
        self.assertEqual(len(t.peticiones), 1)

    def test_get_si_se_reintenta(self) -> None:
        c, t, _ = cliente([(504, ""), (200, {"success": True})])
        c.comprobantes.historial("abc")
        self.assertEqual(len(t.peticiones), 2)


class TestPayload(unittest.TestCase):
    def test_emitir_completa_defaults_sin_mutar_los_datos(self) -> None:
        c, t, _ = cliente([(200, EMISION_OK)])
        original = json.loads(json.dumps(DATOS_BOLETA))
        c.comprobantes.emitir(DATOS_BOLETA)
        self.assertEqual(DATOS_BOLETA, original)
        cuerpo = t.peticiones[0]["cuerpo"]
        self.assertEqual(cuerpo["ruc"], "20123456789")
        self.assertEqual(cuerpo["numero_documento"], "#")
        self.assertEqual(cuerpo["codigo_tipo_moneda"], "PEN")
        self.assertEqual(cuerpo["codigo_tipo_operacion"], "0101")
        ahora = factusmart.hora_peru()
        self.assertEqual(cuerpo["fecha_de_emision"], ahora.strftime("%Y-%m-%d"))
        self.assertRegex(cuerpo["hora_de_emision"], r"^\d{2}:\d{2}:\d{2}$")
        self.assertEqual(ahora.utcoffset().total_seconds(), -5 * 3600)

    def test_emitir_respeta_lo_que_manda_el_usuario(self) -> None:
        c, t, _ = cliente([(200, EMISION_OK)])
        datos = dict(
            DATOS_BOLETA,
            ruc="20999999999",
            numero_documento="15",
            fecha_de_emision="2026-01-02",
            hora_de_emision="08:00:00",
            codigo_tipo_moneda="USD",
            codigo_tipo_operacion="0200",
        )
        c.comprobantes.emitir(datos, ruc="20111111111")
        cuerpo = t.peticiones[0]["cuerpo"]
        for k in ("ruc", "numero_documento", "fecha_de_emision", "hora_de_emision", "codigo_tipo_moneda", "codigo_tipo_operacion"):
            self.assertEqual(cuerpo[k], datos[k])

    def test_ruc_por_llamada_sobreescribe_al_del_constructor(self) -> None:
        c, t, _ = cliente([(200, EMISION_OK), (200, {})])
        c.comprobantes.emitir(DATOS_BOLETA, ruc="20111111111")
        c.series.listar(ruc="20111111111")
        self.assertEqual(t.peticiones[0]["cuerpo"]["ruc"], "20111111111")
        self.assertEqual(urllib.parse.urlparse(t.peticiones[1]["url"]).query, "ruc=20111111111")

    def test_nota_no_lleva_tipo_operacion_por_defecto(self) -> None:
        c, t, _ = cliente([(200, EMISION_OK)])
        c.comprobantes.emitir(dict(DATOS_BOLETA, codigo_tipo_documento="07"))
        self.assertNotIn("codigo_tipo_operacion", t.peticiones[0]["cuerpo"])

    def test_rutas_y_metodos(self) -> None:
        c, t, _ = cliente([(200, {})] * 16 + [(200, b"%PDF-1.4")])
        c.ping()
        c.cuenta.saldo()
        c.series.listar()
        c.comprobantes.listar({"estado": "01", "limite": 5, "antes_de": None})
        c.comprobantes.consultar("id1")
        c.comprobantes.reenviar("id1")
        c.comprobantes.consultar_sunat("id1")
        c.comprobantes.historial("id1")
        c.anulaciones.crear({"documentos": []})
        c.anulaciones.estado("tk/1")
        c.guias.emitir({"serie_documento": "TA01"})
        c.guias.estado("g1")
        c.rucs.listar()
        c.rucs.crear({"ruc": "20609999991"})
        c.rucs.activar("20609999991", True)
        c.comprobantes.emitir(DATOS_BOLETA)
        pdf = c.comprobantes.descargar("id1", "PDF")
        self.assertEqual(pdf, b"%PDF-1.4")
        base = "https://api.test/api/v1/issuer"
        esperado = [
            ("GET", "/ping?ruc=20123456789"),
            ("GET", "/account"),
            ("GET", "/series?ruc=20123456789"),
            ("GET", "/documents?ruc=20123456789&estado=01&limite=5"),
            ("GET", "/documents/id1?ruc=20123456789"),
            ("POST", "/documents/id1/reenviar"),
            ("POST", "/documents/id1/consultar-sunat"),
            ("GET", "/documents/id1/historial?ruc=20123456789"),
            ("POST", "/anulaciones"),
            ("GET", "/anulaciones/tk%2F1/status?ruc=20123456789"),
            ("POST", "/guias"),
            ("GET", "/guias/g1/status?ruc=20123456789"),
            ("GET", "/rucs"),
            ("POST", "/rucs"),
            ("PATCH", "/rucs/20609999991/activation"),
            ("POST", "/documents"),
            ("GET", "/documents/id1/pdf?ruc=20123456789"),
        ]
        self.assertEqual([(p["metodo"], p["url"][len(base):]) for p in t.peticiones], esperado)
        cuerpos = {p["url"][len(base):]: p["cuerpo"] for p in t.peticiones if p["metodo"] != "GET"}
        self.assertEqual(cuerpos["/documents/id1/reenviar"], {"ruc": "20123456789"})
        self.assertEqual(cuerpos["/rucs"], {"ruc": "20609999991"})  # /rucs no lleva RUC emisor
        self.assertEqual(cuerpos["/rucs/20609999991/activation"], {"activo": True})
        guia = cuerpos["/guias"]
        self.assertEqual((guia["ruc"], guia["numero_documento"]), ("20123456789", "#"))
        self.assertNotIn("Idempotency-Key", t.peticiones[10]["headers"])

    def test_descargar_tipo_invalido(self) -> None:
        c, _, _ = cliente([])
        with self.assertRaises(ValueError):
            c.comprobantes.descargar("id1", "zip")


if __name__ == "__main__":
    unittest.main()
