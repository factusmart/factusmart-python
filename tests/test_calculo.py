"""Prueba 9: calcular_comprobante con el caso común de los tres SDK."""

import json
import os
import unittest
from decimal import Decimal

import factusmart

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CASO_COMUN = [
    {"descripcion": "A", "cantidad": 3, "valor_unitario": 10.555, "afectacion": "10"},
    {"descripcion": "B", "cantidad": 2, "valor_unitario": 5, "afectacion": "20"},
    {"descripcion": "C", "cantidad": 1, "valor_unitario": 7.1, "afectacion": "30"},
    {"descripcion": "D", "cantidad": 1, "valor_unitario": 100, "afectacion": "40"},
]

CAMPOS_ITEM = [
    "descripcion", "unidad_de_medida", "cantidad", "valor_unitario", "codigo_tipo_precio",
    "precio_unitario", "codigo_tipo_afectacion_igv", "total_base_igv", "porcentaje_igv",
    "total_igv", "total_impuestos", "total_valor_item", "total_item",
]


class TestCalcularComprobante(unittest.TestCase):
    def test_caso_comun(self) -> None:
        r = factusmart.calcular_comprobante(CASO_COMUN)
        a, b, c, d = r["items"]
        # A: 3 x 10.555 = 31.665 -> 31.67 (ROUND_HALF_UP); IGV 31.67 x 0.18 = 5.7006 -> 5.70
        self.assertEqual(
            a,
            {
                "descripcion": "A", "unidad_de_medida": "NIU", "cantidad": 3, "valor_unitario": 10.56,
                "codigo_tipo_precio": "01", "precio_unitario": 12.45, "codigo_tipo_afectacion_igv": "10",
                "total_base_igv": 31.67, "porcentaje_igv": 18, "total_igv": 5.7, "total_impuestos": 5.7,
                "total_valor_item": 31.67, "total_item": 37.37,
            },
        )
        self.assertEqual((b["total_valor_item"], b["total_igv"], b["porcentaje_igv"], b["total_item"]), (10.0, 0.0, 0, 10.0))
        self.assertEqual((c["total_valor_item"], c["total_igv"], c["precio_unitario"], c["total_item"]), (7.1, 0.0, 7.1, 7.1))
        self.assertEqual((d["codigo_tipo_afectacion_igv"], d["total_igv"], d["total_item"]), ("40", 0.0, 100.0))
        for it in r["items"]:
            self.assertEqual(list(it.keys()), CAMPOS_ITEM)
        self.assertEqual(
            r["totales"],
            {
                "total_operaciones_gravadas": 31.67,
                "total_operaciones_exoneradas": 10.0,
                "total_operaciones_inafectas": 7.1,
                "total_exportacion": 100.0,
                "total_igv": 5.7,
                "total_impuestos": 5.7,
                "total_valor": 148.77,
                "total_venta": 154.47,
            },
        )
        # Guarda el resultado para compararlo con los SDK de PHP y Node.
        with open(os.path.join(RAIZ, "resultado_caso_comun.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def test_codigo_interno_y_unidad(self) -> None:
        r = factusmart.calcular_comprobante(
            [{"codigo_interno": "P1", "descripcion": "x", "cantidad": 1, "valor_unitario": 100, "afectacion": "10", "unidad_de_medida": "ZZ"}]
        )
        it = r["items"][0]
        self.assertEqual(list(it.keys())[0], "codigo_interno")
        self.assertEqual((it["codigo_interno"], it["unidad_de_medida"], it["precio_unitario"], it["total_item"]), ("P1", "ZZ", 118.0, 118.0))
        self.assertEqual(r["totales"]["total_venta"], 118.0)

    def test_redondeo_half_up_sin_error_de_float(self) -> None:
        # 1.005 en float es 1.00499999...; con Decimal(str()) se redondea a 1.01
        r = factusmart.calcular_comprobante([{"descripcion": "x", "cantidad": 1, "valor_unitario": 1.005, "afectacion": "20"}])
        self.assertEqual(r["items"][0]["total_valor_item"], 1.01)
        r = factusmart.calcular_comprobante([{"descripcion": "x", "cantidad": "2", "valor_unitario": Decimal("0.125"), "afectacion": "30"}])
        self.assertEqual(r["items"][0]["total_valor_item"], 0.25)

    def test_entradas_invalidas(self) -> None:
        with self.assertRaises(ValueError):
            factusmart.calcular_comprobante([])
        with self.assertRaises(ValueError):
            factusmart.calcular_comprobante([{"descripcion": "x", "cantidad": 1, "valor_unitario": 1, "afectacion": "11"}])
        with self.assertRaises(ValueError):
            factusmart.calcular_comprobante([{"descripcion": "x", "cantidad": 1, "afectacion": "10"}])


if __name__ == "__main__":
    unittest.main()
