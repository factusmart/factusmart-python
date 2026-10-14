# Cambios

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

## 0.1.x

- Primera versión publicada: cliente con todos los endpoints del API,
  `calcular_comprobante`, excepciones por código HTTP, reintentos con
  `Idempotency-Key` y cero dependencias.
