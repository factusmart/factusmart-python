# Cambios

## 0.5.0 — 2026-11-10

- `rucs.configurar_sunat` acepta `modalidad` (`propio` | `pse`), `pse_usuario`
  y `pse_clave` (solo por nombre; la firma anterior no cambia). Con
  `modalidad="pse"` Smart PSE firma y envía por ti, sin certificado propio.
  Nueva constante `factusmart.recursos.MODALIDADES`.
- Validación local: `pse_usuario` y `pse_clave` van juntos; `modalidad` debe ser
  `propio` o `pse`. `modalidad="pse"` sin credenciales se manda tal cual (el
  API lo permite sobre un RUC ya en PSE).
- `entorno="demo"` se acepta (sinónimo de `prueba` en el API); `ENTORNOS`
  ahora incluye `demo`.
- La `pse_clave` se tapa (`***`) en las excepciones, igual que la `clave_sol`.
  El PUT sigue sin reintentarse.
- Respuestas: `configuracion`/`configurar_sunat` traen `modalidad`, `pse`
  (`proveedor`, `configurado`, `usuario` enmascarado; `None` si no es PSE) y,
  en el PUT, `aviso`; `verificar` trae `modalidad` y `checks["pse"]`.
- `tests/fixtures/openapi.yaml` actualizado a la spec actual.

## 0.4.0 — 2026-11-10

- Configuración del RUC por API (tag «Configuración del RUC»), en el grupo `rucs`:
  - `subir_certificado(ruc, certificado, clave)` (`PUT /rucs/{ruc}/certificado`):
    `certificado` es la ruta del .pfx/.p12 (`str` o `Path`) o sus `bytes`; el
    SDK lo lee y lo manda en base64. Ruta inexistente: `ErrorDeValidacion`
    sin llamar al API.
  - `configurar_sunat(ruc, usuario_sol=None, clave_sol=None, entorno=None)`
    (`PUT /rucs/{ruc}/sunat`): manda solo lo que pases; `entorno` `prueba` o
    `produccion` (`factusmart.recursos.ENTORNOS`).
  - `verificar(ruc)` (`POST /rucs/{ruc}/verificar`): prueba certificado y SOL
    contra SUNAT sin emitir; se reintenta como una consulta.
  - `configuracion(ruc)` (`GET /rucs/{ruc}/configuracion`).
- La clave del certificado, la `clave_sol` y el contenido del certificado se
  tapan (`***`) en el mensaje, `respuesta` y `campos` de cualquier excepción de
  esas llamadas. `subir_certificado` y `configurar_sunat` nunca se reintentan solas.
- `tests/fixtures/openapi.yaml` actualizado a la spec actual.

## 0.3.0 — 2026-11-06

- Nuevo recurso `consultas` (`GET /consultas/{tipo}/{numero}`):
  `ruc(numero)`, `dni(numero)` y `documento(tipo, numero)`. Devuelve nombre,
  dirección, estado, condición, ubigeo, `desde_cache`, `consultas_restantes`,
  `periodo` y `se_renueva`. No manda RUC emisor y se reintenta como una
  consulta GET.
- Nuevos códigos en `CodigoDeError`: `LIMITE_CONSULTAS` (429, no reintentable:
  se lanza `LimiteDePeticiones` tras una sola petición) y
  `CONSULTA_NO_DISPONIBLE` (503, reintentable).
- Nuevo `Cliente.raiz()` (`GET /`, operación `apiRoot`): confirma que el API
  responde, sin llave ni RUC.
- `tests/fixtures/openapi.yaml` actualizado a la spec actual.

## 0.2.0 — 2026-10-14

- Los errores traen `codigo` (identificador estable en MAYÚSCULAS, p. ej.
  `NO_ENCONTRADO`), `reintentable` (`True`/`False`, o `None` si el servidor no
  lo envía) y `campos` (detalle por campo en los 422; `{}` si no hay). Nueva
  clase `CodigoDeError` con los códigos conocidos.
- Reintentos: en las operaciones que ya se reintentaban (consultas GET,
  `comprobantes.emitir` con su misma `Idempotency-Key` y `rucs.crear`) también
  se reintenta cuando la respuesta trae `"reintentable": true` (por ejemplo
  `ERROR_INTERNO` o `SUNAT_NO_DISPONIBLE`). Las operaciones que nunca se
  reintentan solas siguen igual.
- Límite de peticiones: se lee también `retry_after` del cuerpo.
- Nueva función `factusmart.verificar_firma_webhook(cuerpo_crudo, firma, secreto)`
  (también `Cliente.verificar_firma_webhook`) para validar el header
  `X-FactuSmart-Firma` de los webhooks.
- `comprobantes.descargar()` de un comprobante inexistente: el API ahora
  responde 404 en JSON; se lanza `NoEncontrado` con su `message` y
  `codigo="NO_ENCONTRADO"`.
- Nuevo `comprobantes.calcular(items, porcentaje_igv=None)` (`POST /calcular`):
  calcula `items` y `totales` en el servidor sin emitir ni cobrar. Admite
  `precio_unitario` con IGV y la tasa reducida de 10.5 % (Ley 31556). No manda
  RUC y se reintenta como una consulta. `calcular_comprobante` (local, sin red)
  se mantiene.
- Nuevo recurso `catalogos`: `listar(ruc=None)` (`GET /catalogos`) y
  `consultar(nombre, q=None, ruc=None)` (`GET /catalogos/{nombre}`).
- `"reintentable": false` en una respuesta de error manda: no se reintenta
  nunca, aunque el HTTP sea 429/409/5xx. Un `429` con `codigo`
  `LIMITE_PRUEBAS_DIARIO` lanza `LimiteDePeticiones` tras una sola petición.
- `comprobantes.descargar(id, "pdf", formato="ticket")`: PDF en `a4`, `a5`,
  `ticket` (= `ticket80`), `ticket80`, `ticket58` o `ticket50`
  (`?formato=`). Sin `formato` no se manda nada (A4 de siempre). `formato` con
  `xml`/`cdr` o un valor fuera de la lista lanza `ErrorDeValidacion` (422,
  `DATOS_INVALIDOS`, `campos["formato"]`) sin hacer la petición.
- Nuevo recurso `establecimientos` (anexos): `listar(ruc=None)`
  (`GET /establecimientos`, se reintenta como GET) y `crear(datos, ruc=None)`
  (`POST /establecimientos`, `ruc` en el cuerpo, nunca se reintenta solo).
- Nuevo `catalogos.buscar_producto_sunat(q, limite=None, ruc=None)`
  (`GET /catalogos/productos-sunat`, catálogo SUNAT 25, máx. 50 filas).
- `CodigoDeError` suma `PDF_NO_GENERADO` y `LIMITE_ESTABLECIMIENTOS`.
- `CodigoDeError`: nuevos `LIMITE_PRUEBAS_DIARIO`, `ANULACION_MIXTA` y
  `LLAVE_DE_PRUEBA_EN_PRODUCCION`.
- `anulaciones.crear` documenta que también anula boletas (resumen diario) y
  que la respuesta trae `tipo` (`baja` | `resumen`) e `identificador`.
- En RUCs demo el API ya no cobra crédito (`credito_cobrado: False`); la prueba
  de idempotencia ya no depende de que baje el saldo.

## 0.1.x

- Primera versión publicada: cliente con todos los endpoints del API,
  `calcular_comprobante`, excepciones por código HTTP, reintentos con
  `Idempotency-Key` y cero dependencias.
