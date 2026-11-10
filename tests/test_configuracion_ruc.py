"""rucs.subir_certificado / configurar_sunat / verificar / configuracion, sin red."""

import base64
import os
import pathlib
import tempfile
import unittest

import factusmart
from factusmart import errores
from test_unitarios import cliente

BASE = "https://api.test/api/v1/issuer"
RUC = "20777666555"
CLAVE = "ClaveDelPfx-Secreta"
CLAVE_SOL = "ClaveSol9xyz"
PFX = b"\x30\x82\x0a\x5e\x02\x01\x03 contenido-binario-del-pfx \xff\x00"

CERT_OK = {
    "success": True,
    "ruc": RUC,
    "certificado": {
        "instalado": True,
        "titular": "API TENANT CLEAN SAC",
        "vence": "2027-11-10",
        "dias_para_vencer": 364,
        "ruc_coincide": True,
    },
}

CONFIG_OK = {
    "success": True,
    "ruc": RUC,
    "nombre": "API TENANT CLEAN SAC",
    "entorno": "produccion",
    "certificado": {"instalado": True, "vence": "2027-11-10", "dias_para_vencer": 364},
    "sol": {"configurado": True, "usuario": "FA*****1"},
    "envio": "sunat",
    "listo_para_produccion": True,
    "faltantes": [],
}

VERIFICAR_OK = {
    "success": True,
    "ruc": RUC,
    "listo_para_emitir": False,
    "entorno": "produccion",
    "checks": {
        "certificado": {"ok": True, "mensaje": "Certificado vigente hasta el 2027-11-10 (364 días)."},
        "sol": {"ok": False, "mensaje": "SUNAT rechazó el usuario o la clave SOL."},
    },
}


def _sin_x_ruc(test: unittest.TestCase, peticion) -> None:
    test.assertNotIn("X-RUC", {k.upper(): v for k, v in peticion["headers"].items()})
    test.assertNotIn("?", peticion["url"])  # ni ?ruc= del cliente


class TestSubirCertificado(unittest.TestCase):
    def test_desde_bytes(self) -> None:
        c, t, _ = cliente([(200, CERT_OK)])
        r = c.rucs.subir_certificado(RUC, PFX, CLAVE)
        p = t.peticiones[0]
        self.assertEqual(p["metodo"], "PUT")
        self.assertEqual(p["url"], BASE + "/rucs/20777666555/certificado")
        self.assertEqual(p["cuerpo"], {"certificado": base64.b64encode(PFX).decode("ascii"), "clave": CLAVE})
        self.assertEqual(base64.b64decode(p["cuerpo"]["certificado"]), PFX)
        _sin_x_ruc(self, p)
        self.assertTrue(r["certificado"]["ruc_coincide"])

    def test_desde_ruta_str_y_path(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "mi certificado.pfx")
            with open(ruta, "wb") as f:
                f.write(PFX)
            for valor in (ruta, pathlib.Path(ruta)):
                with self.subTest(tipo=type(valor).__name__):
                    c, t, _ = cliente([(200, CERT_OK)])
                    c.rucs.subir_certificado(RUC, valor, CLAVE)
                    self.assertEqual(base64.b64decode(t.peticiones[0]["cuerpo"]["certificado"]), PFX)

    def test_bytearray(self) -> None:
        c, t, _ = cliente([(200, CERT_OK)])
        c.rucs.subir_certificado(RUC, bytearray(PFX), CLAVE)
        self.assertEqual(base64.b64decode(t.peticiones[0]["cuerpo"]["certificado"]), PFX)

    def test_ruta_inexistente_no_llama_y_no_muestra_la_clave(self) -> None:
        c, t, _ = cliente([])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.rucs.subir_certificado(RUC, "C:/no/existe/cert.pfx", CLAVE)
        e = ctx.exception
        self.assertIn("No se encontró", str(e))
        self.assertIn("cert.pfx", str(e))
        self.assertNotIn(CLAVE, str(e) + repr(e) + repr(e.campos))
        self.assertEqual(e.codigo, "DATOS_INVALIDOS")
        self.assertIn("certificado", e.campos)
        self.assertEqual(t.peticiones, [])

    def test_tipo_invalido(self) -> None:
        c, _, _ = cliente([])
        with self.assertRaises(TypeError):
            c.rucs.subir_certificado(RUC, 123, CLAVE)  # type: ignore[arg-type]

    def test_422_no_filtra_clave_ni_certificado(self) -> None:
        b64 = base64.b64encode(PFX).decode("ascii")
        # Respuesta hostil que hace eco de lo enviado (el API real no lo hace).
        eco = {
            "success": False,
            "message": "El certificado no abre con la clave {} ({})".format(CLAVE, b64),
            "codigo": "DATOS_INVALIDOS",
            "reintentable": False,
            "campos": {"clave": ["clave recibida: " + CLAVE]},
            "recibido": {"clave": CLAVE, "certificado": b64},
        }
        c, t, _ = cliente([(422, eco)])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.rucs.subir_certificado(RUC, PFX, CLAVE)
        e = ctx.exception
        todo = " ".join([str(e), repr(e), repr(e.args), repr(e.respuesta), repr(e.campos), e.mensaje])
        self.assertNotIn(CLAVE, todo)
        self.assertNotIn(b64, todo)
        self.assertEqual(e.status, 422)
        self.assertEqual(e.codigo, "DATOS_INVALIDOS")
        self.assertIn("***", e.mensaje)
        self.assertEqual(len(t.peticiones), 1)  # nunca se reintenta

    def test_no_se_reintenta_ante_503(self) -> None:
        c, t, _ = cliente([(503, {"success": False, "message": "Service Unavailable"})])
        with self.assertRaises(factusmart.FactuSmartError):
            c.rucs.subir_certificado(RUC, PFX, CLAVE)
        self.assertEqual(len(t.peticiones), 1)


class TestConfigurarSunat(unittest.TestCase):
    def test_sol_y_entorno(self) -> None:
        c, t, _ = cliente([(200, CONFIG_OK)])
        r = c.rucs.configurar_sunat(RUC, usuario_sol="FACTURA1", clave_sol=CLAVE_SOL, entorno="produccion")
        p = t.peticiones[0]
        self.assertEqual(p["metodo"], "PUT")
        self.assertEqual(p["url"], BASE + "/rucs/20777666555/sunat")
        self.assertEqual(p["cuerpo"], {"usuario_sol": "FACTURA1", "clave_sol": CLAVE_SOL, "entorno": "produccion"})
        _sin_x_ruc(self, p)
        self.assertEqual(r["sol"]["usuario"], "FA*****1")

    def test_solo_manda_lo_dado(self) -> None:
        c, t, _ = cliente([(200, CONFIG_OK), (200, CONFIG_OK)])
        c.rucs.configurar_sunat(RUC, entorno="prueba")
        c.rucs.configurar_sunat(RUC, usuario_sol="FACTURA1", clave_sol=CLAVE_SOL)
        self.assertEqual(t.peticiones[0]["cuerpo"], {"entorno": "prueba"})
        self.assertEqual(t.peticiones[1]["cuerpo"], {"usuario_sol": "FACTURA1", "clave_sol": CLAVE_SOL})

    def test_validaciones_locales(self) -> None:
        c, t, _ = cliente([])
        casos = [
            dict(),
            dict(usuario_sol="FACTURA1"),
            dict(clave_sol=CLAVE_SOL),
            dict(entorno="real"),
        ]
        for kw in casos:
            with self.subTest(kw=sorted(kw)):
                with self.assertRaises(errores.ErrorDeValidacion) as ctx:
                    c.rucs.configurar_sunat(RUC, **kw)
                self.assertNotIn(CLAVE_SOL, str(ctx.exception) + repr(ctx.exception.campos))
        self.assertEqual(t.peticiones, [])

    def test_422_faltantes_sin_filtrar_clave_sol(self) -> None:
        resp = {
            "success": False,
            "message": "Para pasar a producción falta: certificado. (clave " + CLAVE_SOL + ")",
            "codigo": "DATOS_INVALIDOS",
            "reintentable": False,
            "campos": {"entorno": ["Falta: certificado"]},
            "faltantes": ["certificado"],
        }
        c, t, _ = cliente([(422, resp)])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.rucs.configurar_sunat(RUC, usuario_sol="FACTURA1", clave_sol=CLAVE_SOL, entorno="produccion")
        e = ctx.exception
        self.assertNotIn(CLAVE_SOL, " ".join([str(e), repr(e), repr(e.respuesta), repr(e.campos)]))
        self.assertEqual(e.respuesta["faltantes"], ["certificado"])
        self.assertEqual(e.campos, {"entorno": ["Falta: certificado"]})
        self.assertEqual(len(t.peticiones), 1)


PSE_USUARIO = "FURZQQ7F"
PSE_CLAVE = "379VMR6U"
AVISO_PSE = (
    "Con Smart PSE el contribuyente debe designar a Smart PSE como su Proveedor de Servicios "
    "Electrónicos (PSE) en SUNAT Operaciones en Línea, con su Clave SOL."
)
CONFIG_PSE = {
    "success": True,
    "ruc": RUC,
    "nombre": "API TENANT CLEAN SAC",
    "entorno": "produccion",
    "certificado": {"instalado": False, "vence": None, "dias_para_vencer": None},
    "sol": {"configurado": False, "usuario": None},
    "envio": "pse",
    "modalidad": "pse",
    "pse": {"proveedor": "smartpse", "configurado": True, "usuario": "FU*****F"},
    "listo_para_produccion": True,
    "faltantes": [],
    "aviso": AVISO_PSE,
}
VERIFICAR_PSE = {
    "success": True,
    "ruc": RUC,
    "listo_para_emitir": True,
    "entorno": "produccion",
    "modalidad": "pse",
    "checks": {
        "certificado": {"ok": None, "mensaje": "Firma Smart PSE: no hace falta certificado propio."},
        "sol": {"ok": None, "mensaje": "Sin usuario SOL (recomendado para guías)."},
        "pse": {"ok": True, "mensaje": "Smart PSE aceptó las credenciales."},
    },
}


class TestConfigurarSunatPse(unittest.TestCase):
    def test_cuerpo_exacto_pse(self) -> None:
        c, t, _ = cliente([(200, CONFIG_PSE)])
        r = c.rucs.configurar_sunat(
            RUC, modalidad="pse", pse_usuario=PSE_USUARIO, pse_clave=PSE_CLAVE, entorno="produccion"
        )
        p = t.peticiones[0]
        self.assertEqual(p["metodo"], "PUT")
        self.assertEqual(p["url"], BASE + "/rucs/20777666555/sunat")
        self.assertEqual(
            p["cuerpo"],
            {"modalidad": "pse", "pse_usuario": PSE_USUARIO, "pse_clave": PSE_CLAVE, "entorno": "produccion"},
        )
        _sin_x_ruc(self, p)
        self.assertEqual(r["modalidad"], "pse")
        self.assertEqual(r["envio"], "pse")
        self.assertEqual(r["pse"], {"proveedor": "smartpse", "configurado": True, "usuario": "FU*****F"})
        self.assertIn("designar a Smart PSE", r["aviso"])

    def test_modalidad_sin_credenciales_y_propio(self) -> None:
        # Repetir modalidad pse sin credenciales lo permite el API: el SDK no lo bloquea.
        c, t, _ = cliente([(200, CONFIG_PSE), (200, dict(CONFIG_OK, modalidad="propio", pse=None))])
        c.rucs.configurar_sunat(RUC, modalidad="pse")
        r = c.rucs.configurar_sunat(RUC, modalidad="propio")
        self.assertEqual(t.peticiones[0]["cuerpo"], {"modalidad": "pse"})
        self.assertEqual(t.peticiones[1]["cuerpo"], {"modalidad": "propio"})
        self.assertIsNone(r["pse"])

    def test_pse_sin_modalidad_lo_decide_el_api(self) -> None:
        c, t, _ = cliente([(200, CONFIG_PSE)])
        c.rucs.configurar_sunat(RUC, pse_usuario=PSE_USUARIO, pse_clave=PSE_CLAVE)
        self.assertEqual(t.peticiones[0]["cuerpo"], {"pse_usuario": PSE_USUARIO, "pse_clave": PSE_CLAVE})

    def test_entorno_demo_aceptado(self) -> None:
        c, t, _ = cliente([(200, CONFIG_OK)])
        c.rucs.configurar_sunat(RUC, entorno="demo")
        self.assertEqual(t.peticiones[0]["cuerpo"], {"entorno": "demo"})
        self.assertIn("demo", factusmart.recursos.ENTORNOS)

    def test_validaciones_locales_pse(self) -> None:
        c, t, _ = cliente([])
        casos = [
            dict(pse_usuario=PSE_USUARIO),
            dict(pse_clave=PSE_CLAVE),
            dict(modalidad="pse", pse_usuario=PSE_USUARIO),
            dict(modalidad="pse", pse_clave=PSE_CLAVE),
            dict(modalidad="otro"),
            dict(modalidad="PSE"),
        ]
        for kw in casos:
            with self.subTest(kw=repr(sorted(kw.items()))):
                with self.assertRaises(errores.ErrorDeValidacion) as ctx:
                    c.rucs.configurar_sunat(RUC, **kw)
                e = ctx.exception
                self.assertEqual(e.codigo, "DATOS_INVALIDOS")
                self.assertNotIn(PSE_CLAVE, str(e) + repr(e.campos))
        self.assertEqual(t.peticiones, [])

    def test_pse_usuario_sin_clave_senala_el_campo(self) -> None:
        c, t, _ = cliente([])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.rucs.configurar_sunat(RUC, modalidad="pse", pse_usuario=PSE_USUARIO)
        self.assertIn("pse_clave", ctx.exception.campos)
        self.assertEqual(t.peticiones, [])

    def test_422_no_filtra_pse_clave_ni_clave_sol(self) -> None:
        eco = {
            "success": False,
            "message": "Smart PSE rechazó {} / {} (clave {})".format(PSE_USUARIO, PSE_CLAVE, CLAVE_SOL),
            "codigo": "DATOS_INVALIDOS",
            "reintentable": False,
            "campos": {"pse_clave": ["recibida: " + PSE_CLAVE]},
            "recibido": {"pse_clave": PSE_CLAVE, "clave_sol": CLAVE_SOL},
        }
        c, t, _ = cliente([(422, eco)])
        with self.assertRaises(errores.ErrorDeValidacion) as ctx:
            c.rucs.configurar_sunat(
                RUC,
                usuario_sol="FACTURA1",
                clave_sol=CLAVE_SOL,
                modalidad="pse",
                pse_usuario=PSE_USUARIO,
                pse_clave=PSE_CLAVE,
            )
        e = ctx.exception
        todo = " ".join([str(e), repr(e), repr(e.args), repr(e.respuesta), repr(e.campos), e.mensaje])
        self.assertNotIn(PSE_CLAVE, todo)
        self.assertNotIn(CLAVE_SOL, todo)
        self.assertIn("***", e.mensaje)
        self.assertIn("pse_clave", e.campos)
        self.assertEqual(len(t.peticiones), 1)

    def test_put_pse_no_se_reintenta_ante_5xx(self) -> None:
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                c, t, esperas = cliente([(status, {"success": False, "message": "x " + PSE_CLAVE})])
                with self.assertRaises(factusmart.FactuSmartError) as ctx:
                    c.rucs.configurar_sunat(RUC, modalidad="pse", pse_usuario=PSE_USUARIO, pse_clave=PSE_CLAVE)
                self.assertNotIn(PSE_CLAVE, str(ctx.exception))
                self.assertEqual(len(t.peticiones), 1)
                self.assertEqual(esperas, [])

    def test_firma_posicional_intacta(self) -> None:
        c, t, _ = cliente([(200, CONFIG_OK)])
        c.rucs.configurar_sunat(RUC, "FACTURA1", CLAVE_SOL, "prueba")
        self.assertEqual(
            t.peticiones[0]["cuerpo"], {"usuario_sol": "FACTURA1", "clave_sol": CLAVE_SOL, "entorno": "prueba"}
        )

    def test_verificar_con_check_pse(self) -> None:
        c, _, _ = cliente([(200, VERIFICAR_PSE)])
        r = c.rucs.verificar(RUC)
        self.assertEqual(r["modalidad"], "pse")
        self.assertTrue(r["checks"]["pse"]["ok"])


class TestVerificarYConfiguracion(unittest.TestCase):
    def test_verificar_post_sin_cuerpo(self) -> None:
        c, t, _ = cliente([(200, VERIFICAR_OK)])
        r = c.rucs.verificar(RUC)
        p = t.peticiones[0]
        self.assertEqual(p["metodo"], "POST")
        self.assertEqual(p["url"], BASE + "/rucs/20777666555/verificar")
        self.assertIsNone(p["cuerpo"])
        _sin_x_ruc(self, p)
        self.assertFalse(r["checks"]["sol"]["ok"])
        self.assertFalse(r["listo_para_emitir"])

    def test_verificar_se_reintenta_ante_503(self) -> None:
        c, t, esperas = cliente([(503, {"success": False, "message": "x"}), (200, VERIFICAR_OK)])
        c.rucs.verificar(RUC)
        self.assertEqual(len(t.peticiones), 2)
        self.assertEqual(esperas, [1.0])

    def test_configuracion_get(self) -> None:
        c, t, _ = cliente([(200, CONFIG_OK)])
        r = c.rucs.configuracion(RUC)
        p = t.peticiones[0]
        self.assertEqual(p["metodo"], "GET")
        self.assertEqual(p["url"], BASE + "/rucs/20777666555/configuracion")
        _sin_x_ruc(self, p)
        self.assertTrue(r["listo_para_produccion"])
        self.assertEqual(r["faltantes"], [])

    def test_ruc_inexistente(self) -> None:
        c, _, _ = cliente([(404, {"success": False, "message": "Ese RUC no pertenece a esta cuenta o no existe.", "codigo": "NO_ENCONTRADO"})])
        with self.assertRaises(errores.NoEncontrado):
            c.rucs.configuracion("20000000001")

    def test_mapeo_de_operaciones(self) -> None:
        esperado = {
            "uploadRucCertificate": "rucs.subir_certificado",
            "updateRucSunat": "rucs.configurar_sunat",
            "verifyRucConfig": "rucs.verificar",
            "getRucConfig": "rucs.configuracion",
        }
        for op, metodo in esperado.items():
            self.assertEqual(factusmart.OPERACIONES.get(op), metodo)

    def test_user_agent_060(self) -> None:
        c, t, _ = cliente([(200, CONFIG_OK)])
        c.rucs.configuracion(RUC)
        self.assertEqual(t.peticiones[0]["headers"]["User-Agent"], "factusmart-python/0.6.0")
        self.assertEqual(factusmart.__version__, "0.6.0")


class TestConfirmarYCodigosNuevos(unittest.TestCase):
    def test_confirmar_solo_se_envia_si_se_pasa(self) -> None:
        sin_confirmar = {"success": False, "message": "El RUC emite en producción. Repite con confirmar: true.",
                         "codigo": "CONFIRMAR_CAMBIO_ENTORNO", "reintentable": False}
        c, t, esperas = cliente([(422, sin_confirmar), (200, dict(CONFIG_OK, aviso="Pasó a prueba."))])
        with self.assertRaises(factusmart.ErrorDeValidacion) as ctx:
            c.rucs.configurar_sunat(RUC, entorno="prueba")
        self.assertEqual(ctx.exception.codigo, factusmart.CodigoDeError.CONFIRMAR_CAMBIO_ENTORNO)
        self.assertFalse(ctx.exception.reintentable)
        self.assertEqual(len(t.peticiones), 1)
        self.assertEqual(t.peticiones[0]["cuerpo"], {"entorno": "prueba"})
        r = c.rucs.configurar_sunat(RUC, entorno="prueba", confirmar=True)
        self.assertEqual(t.peticiones[1]["cuerpo"], {"entorno": "prueba", "confirmar": True})
        self.assertEqual(r["aviso"], "Pasó a prueba.")
        self.assertEqual(esperas, [])

    def test_confirmar_solo_o_invalido_no_llama(self) -> None:
        c, t, _ = cliente([])
        with self.assertRaises(factusmart.ErrorDeValidacion):
            c.rucs.configurar_sunat(RUC, confirmar=True)
        with self.assertRaises(factusmart.ErrorDeValidacion) as ctx:
            c.rucs.configurar_sunat(RUC, entorno="prueba", confirmar="si")  # type: ignore[arg-type]
        self.assertIn("confirmar", ctx.exception.campos)
        self.assertEqual(t.peticiones, [])

    def test_limite_verificaciones_no_se_reintenta_y_trae_la_espera(self) -> None:
        cuerpo = {"success": False, "message": "Hiciste más de 10 verificaciones en una hora para este RUC.",
                  "retry_after": 1800, "codigo": "LIMITE_VERIFICACIONES", "reintentable": True}
        c, t, esperas = cliente([(429, cuerpo, {"Retry-After": "1800"}), (200, VERIFICAR_OK)])
        with self.assertRaises(factusmart.LimiteDePeticiones) as ctx:
            c.rucs.verificar(RUC)
        e = ctx.exception
        self.assertEqual(e.codigo, factusmart.CodigoDeError.LIMITE_VERIFICACIONES)
        self.assertEqual(e.segundos_de_espera, 1800)
        self.assertTrue(e.reintentable)
        self.assertEqual(len(t.peticiones), 1)
        self.assertEqual(esperas, [])

    def test_pse_no_disponible_y_ruc_desactivado(self) -> None:
        caido = {"success": False, "message": "Smart PSE no respondió.", "codigo": "PSE_NO_DISPONIBLE", "reintentable": True}
        bloqueado = {"success": False, "message": "Este RUC está desactivado o su plan venció.",
                     "codigo": "RUC_DESACTIVADO", "reintentable": False}
        c, t, _ = cliente([(503, caido), (403, bloqueado)])
        with self.assertRaises(factusmart.FactuSmartError) as ctx:
            c.rucs.configurar_sunat(RUC, modalidad="pse", pse_usuario="FURZQQ7F", pse_clave="379VMR6U")
        self.assertEqual(ctx.exception.codigo, factusmart.CodigoDeError.PSE_NO_DISPONIBLE)
        self.assertTrue(ctx.exception.reintentable)
        self.assertEqual(len(t.peticiones), 1)
        with self.assertRaises(factusmart.RucNoAutorizado) as ctx2:
            c.rucs.verificar(RUC)
        self.assertEqual(ctx2.exception.codigo, factusmart.CodigoDeError.RUC_DESACTIVADO)


if __name__ == "__main__":
    unittest.main()
