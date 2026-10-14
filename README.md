# FactuSmart — SDK de Python

SDK oficial del **API de facturación electrónica de FactuSmart** (SUNAT, Perú):
facturas, boletas, notas de crédito/débito, guías de remisión (GRE 2.0) y
anulaciones.

- Python 3.8 o superior.
- **Cero dependencias**: solo librería estándar (`urllib`).
- Con type hints (`py.typed`).
- Documentación completa del API: https://factusmart.pe/api-facturacion-electronica/docs

## Instalar

```bash
pip install factusmart
```

## Uso en 10 líneas

```python
import factusmart

fs = factusmart.Cliente(api_key="TU_API_KEY", base_url="https://TU_URL_BASE/api/v1/issuer", ruc="20123456789")

calc = factusmart.calcular_comprobante([
    {"descripcion": "Servicio de consultoría", "cantidad": 1, "valor_unitario": 100, "afectacion": "10"},
])

r = fs.comprobantes.emitir({
    "codigo_tipo_documento": "01",
    "datos_del_cliente_o_receptor": {"codigo_tipo_documento_identidad": "6", "numero_documento": "20555555555"},
    "items": calc["items"], "totales": calc["totales"],
})

print(r["aceptado_por_sunat"], r["serie_numero"])
```

`base_url` **no es igual para todas las cuentas**: cada cuenta vive en un
servidor distinto. Cópiala de tu panel de integrador (pestaña Configuración,
"URL base de la API").

## Opciones del cliente

| Opción | Obligatoria | Por defecto | Para qué |
|---|---|---|---|
| `api_key` | sí | — | Tu API key (va en el header `X-API-Key`) |
| `base_url` | sí | — | URL base de tu cuenta, sin barra final |
| `ruc` | no | — | RUC emisor por defecto. Se cambia en cada llamada con `ruc=` |
| `timeout` | no | `60` | Segundos por petición (SUNAT a veces tarda) |
| `max_reintentos` | no | `3` | Ver "Reintentos e idempotencia" |
| `verificar_ssl` | no | `True` | `False` **solo** en pruebas locales con certificado propio |

Si falta `api_key` o `base_url`, el cliente lanza `ValueError` al crearse.

## Métodos

Los datos se envían y se reciben **tal cual los define el API** (claves en
español con guion bajo). Todos los métodos que operan sobre un RUC aceptan
`ruc=` para cambiar el del constructor (en GET va como `?ruc=`; en POST va en el
cuerpo, y si tú ya pusiste `ruc` en los datos, se respeta el tuyo).

| Método | Endpoint | Devuelve |
|---|---|---|
| `fs.ping(ruc=None)` | `GET /ping` | dict |
| `fs.cuenta.saldo()` | `GET /account` | dict |
| `fs.series.listar(ruc=None)` | `GET /series` | dict |
| `fs.comprobantes.emitir(datos, ruc=None, idempotency_key=None)` | `POST /documents` | dict |
| `fs.comprobantes.listar(filtros=None, ruc=None)` | `GET /documents` | dict |
| `fs.comprobantes.consultar(external_id, ruc=None)` | `GET /documents/{id}` | dict |
| `fs.comprobantes.descargar(external_id, tipo, ruc=None)` | `GET /documents/{id}/{pdf\|xml\|cdr}` | **bytes** |
| `fs.comprobantes.reenviar(external_id, ruc=None)` | `POST /documents/{id}/reenviar` | dict |
| `fs.comprobantes.consultar_sunat(external_id, ruc=None)` | `POST /documents/{id}/consultar-sunat` | dict |
| `fs.comprobantes.historial(external_id, ruc=None)` | `GET /documents/{id}/historial` | dict |
| `fs.anulaciones.crear(datos, ruc=None)` | `POST /anulaciones` | dict |
| `fs.anulaciones.estado(ticket, ruc=None)` | `GET /anulaciones/{ticket}/status` | dict |
| `fs.guias.emitir(datos, ruc=None)` | `POST /guias` | dict |
| `fs.guias.estado(external_id, ruc=None)` | `GET /guias/{id}/status` | dict |
| `fs.rucs.listar()` | `GET /rucs` | dict |
| `fs.rucs.crear(datos)` | `POST /rucs` | dict |
| `fs.rucs.activar(ruc, activo)` | `PATCH /rucs/{ruc}/activation` | dict |

Filtros de `comprobantes.listar`: `estado`, `desde`, `hasta` (YYYY-MM-DD),
`limite` (1 a 100) y `antes_de` (pasa el `siguiente_cursor` de la página
anterior).

Guardar el PDF:

```python
with open("comprobante.pdf", "wb") as f:
    f.write(fs.comprobantes.descargar(r["external_id"], "pdf"))
```

### Lo que `comprobantes.emitir` completa por ti

Solo si no lo mandas:

- `numero_documento`: `"#"` (FactuSmart asigna el correlativo). Si mandas tu
  propio número, se respeta.
- `fecha_de_emision` y `hora_de_emision`: fecha y hora **de Perú**
  (America/Lima), no la de tu servidor.
- `codigo_tipo_moneda`: `"PEN"`.
- `codigo_tipo_operacion`: `"0101"` en facturas y boletas (en notas no aplica).

`guias.emitir` completa igual `numero_documento`, `fecha_de_emision` y
`hora_de_emision`.

## Calcular IGV y totales

El API espera los importes ya calculados. `calcular_comprobante` lo hace por ti:
recibe cada ítem con `descripcion`, `cantidad`, `valor_unitario` (**sin IGV**) y
`afectacion`, y devuelve `{"items": [...], "totales": {...}}` listo para enviar.

| `afectacion` | Significado | IGV |
|---|---|---|
| `"10"` | Gravado | 18% |
| `"20"` | Exonerado | 0 |
| `"30"` | Inafecto | 0 |
| `"40"` | Exportación | 0 (va en `total_exportacion`) |

Opcionales por ítem: `codigo_interno` (recomendado: el SKU de tu sistema) y
`unidad_de_medida` (por defecto `NIU`; usa `ZZ` para servicios).

Redondea a 2 decimales por ítem con `decimal.Decimal` y ROUND_HALF_UP, así da
**exactamente los mismos números** que los SDK de PHP y Node.

## La regla de oro: revisa `aceptado_por_sunat`

Un HTTP 200 significa que FactuSmart **generó** tu comprobante, no que SUNAT lo
aceptó. SUNAT puede estar caída o rechazarlo: recibirás `estado: "01"` con
`aceptado_por_sunat: False` y el motivo en `sunat["descripcion"]`.

**Eso NO es una excepción.** El SDK te devuelve la respuesta tal cual y tú
decides:

```python
r = fs.comprobantes.emitir(datos)
if not r["aceptado_por_sunat"]:
    print("SUNAT no lo aceptó todavía:", r.get("sunat"), r.get("accion_requerida"))
    # corrige y reintenta gratis con: fs.comprobantes.reenviar(r["external_id"])
```

Mira también `entorno` (`"prueba"` o `"produccion"`) y `tiene_validez_fiscal`.

## Errores

Todas las excepciones están en `factusmart.errores` (y también en `factusmart`)
y heredan de `FactuSmartError`, que trae:

- `status`: código HTTP (`None` si fue un error de red),
- `mensaje`: el mensaje del API, en español,
- `respuesta`: el cuerpo completo de la respuesta,
- `codigo`: identificador estable en MAYÚSCULAS (`"NO_ENCONTRADO"`,
  `"SIN_CREDITOS"`…). **Decide tu lógica con `codigo`, no con `mensaje`** (el
  texto puede cambiar de redacción). `None` si fue un error de red,
- `reintentable`: `True` si repetir la misma petición más tarde puede
  funcionar, `False` si hay que corregir algo antes. `None` si no hubo
  respuesta o el servidor es de una versión anterior que no lo envía,
- `campos`: en errores de validación (422), `{"campo": ["mensaje", ...]}`;
  `{}` si no hay detalle por campo.

| HTTP | Excepción |
|---|---|
| 401 | `ErrorDeAutenticacion` |
| 402 | `SinCreditos` |
| 403 | `RucNoAutorizado` |
| 404 | `NoEncontrado` |
| 422 | `ErrorDeValidacion` |
| 429 | `LimiteDePeticiones` (con `segundos_de_espera` si se pudo leer) |
| otros / red | `FactuSmartError` |

Códigos más comunes (lista completa en la documentación del API y en
`factusmart.CodigoDeError`):

| `codigo` | HTTP | `reintentable` | Qué hacer |
|---|---|---|---|
| `NO_AUTENTICADO` | 401 | no | Revisa la API key |
| `PLAN_VENCIDO` / `SIN_CREDITOS` | 402 | no | Renueva el plan o recarga créditos |
| `RUC_NO_AUTORIZADO` / `RUC_DESACTIVADO` | 403 | no | Revisa el RUC emisor |
| `NO_ENCONTRADO` | 404 | no | El comprobante/guía/archivo no existe |
| `EMISION_EN_CURSO` | 409 | sí | Reintenta con la misma `Idempotency-Key` |
| `DATOS_INVALIDOS` | 422 | no | Corrige los datos (detalle en `campos`) |
| `SUNAT_NO_DISPONIBLE` | 422 / 5xx | sí | Reintenta más tarde |
| `LIMITE_PETICIONES` | 429 | sí | Espera `segundos_de_espera` |
| `ERROR_INTERNO` | 5xx | sí | Reintenta; si persiste, contacta soporte |

Un `codigo` desconocido trátalo como no reintentable salvo que `reintentable`
diga lo contrario.

```python
from factusmart import errores

try:
    r = fs.comprobantes.emitir(datos)
except errores.ErrorDeValidacion as e:
    print("Datos inválidos:", e.mensaje)   # no se cobró el crédito
    for campo, mensajes in e.campos.items():
        print(" -", campo, mensajes)
except errores.SinCreditos:
    print("Recarga créditos")
except errores.FactuSmartError as e:
    if e.codigo == factusmart.CodigoDeError.SUNAT_NO_DISPONIBLE:
        print("SUNAT caída, intenta más tarde")
    print("Error", e.status, e.codigo, e.mensaje, "reintentable:", e.reintentable)
```

## Reintentos e idempotencia

- `comprobantes.emitir` **siempre** manda el header `Idempotency-Key`: la tuya
  (`idempotency_key="id-de-tu-venta"`) o un UUID v4 generado. **La misma clave
  se usa en todos los reintentos de esa llamada**, así un reintento nunca emite
  dos veces ni cobra dos veces. Si llamas dos veces con la misma clave,
  recibes la misma respuesta.
- Se reintenta solo ante: error de red/timeout, HTTP 429, 502, 503, 504 o una
  respuesta de error con `"reintentable": true` (p. ej. `ERROR_INTERNO`,
  `SUNAT_NO_DISPONIBLE`), con
  espera creciente (1 s, 2 s, 4 s…), hasta `max_reintentos` veces. Ante un
  límite de peticiones se respeta el header `Retry-After` o el "Espera N
  segundos" del mensaje.
- En `emitir`, el HTTP 409 ("ya hay una emisión en curso con esa
  Idempotency-Key") también se reintenta con la misma clave.
- Se reintentan las consultas (GET) y `rucs.crear` (el API es idempotente por
  RUC).
- **Nunca** se reintentan solas: `anulaciones.crear`, `guias.emitir`,
  `comprobantes.reenviar`, `comprobantes.consultar_sunat` y `rucs.activar`,
  **aunque** la respuesta diga `"reintentable": true`. Ahí decides tú (mira
  `e.reintentable`).

## Verificar webhooks

FactuSmart puede avisarte con un POST a tu servidor cuando un comprobante pasa
a aceptado, observado, rechazado o anulado (se configura en tu portal de
integrador, pestaña Webhooks, donde obtienes el secreto `whsec_…`). Cada aviso
trae el header `X-FactuSmart-Firma`; verifícalo antes de confiar en el aviso:

```python
import factusmart
from flask import Flask, request

app = Flask(__name__)
SECRETO = "whsec_..."  # de tu portal; mejor en una variable de entorno

@app.post("/webhooks/factusmart")
def webhook_factusmart():
    cuerpo_crudo = request.get_data()  # bytes TAL CUAL llegaron
    firma = request.headers.get("X-FactuSmart-Firma", "")
    if not factusmart.verificar_firma_webhook(cuerpo_crudo, firma, SECRETO):
        return "firma inválida", 401
    aviso = request.get_json()
    # guarda aviso["id"] para no procesar dos veces el mismo aviso
    return "", 200
```

**Usa el cuerpo CRUDO.** Si haces `json.dumps(request.get_json())` los bytes
cambian (espacios, orden, tildes) y la firma no coincide. La función nunca
lanza excepción: con datos vacíos, `None` o una firma mal formada devuelve
`False`. Responde `2xx` en menos de 8 segundos (si el proceso es largo, hazlo
después).

## Pruebas (para quien mantiene el SDK)

```bash
python -m unittest discover -s tests -v
```

- `test_unitarios.py` y `test_calculo.py` no usan red.
- `test_contrato.py` lee `openapi.yaml` (variable `FACTUSMART_OPENAPI`) y falla
  si algún `operationId` no tiene método en el SDK.
- `test_integracion.py` va contra el API **local** (`FACTUSMART_TEST_BASE_URL`,
  `FACTUSMART_TEST_API_KEY`, `FACTUSMART_TEST_RUC`; `FACTUSMART_INTEGRACION=0`
  para saltarlas). Por defecto usa el RUC `20777666555`. Gasta 2 créditos por corrida. Se niega a correr contra
  `factusmart.pe`.

## Licencia

MIT. Ver [LICENSE](LICENSE).
