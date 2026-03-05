# Ecobus / Ecovan — MVP Control de Pasajeros (Planes + QR + Check-in)

Implementación lista para desplegar en **Render** (API FastAPI + Scanner web + Admin Streamlit) basada en la especificación del 05-03-2026.

## Qué incluye
- **API FastAPI** con lógica de validación centralizada (`/api/validate`) y registro de **check-ins OK/REJECTED**.
- **QR tokens** rotables (se revoca el token anterior al regenerar / activar plan).
- **/scan** (web mobile-first) para el **pasajero encargado**: selecciona `IDA/VUELTA` + `La Colonia / Cruce Malloco` + cámara.
- **Admin Streamlit**: dashboard del día, pasajeros, planes mensuales, pase diario.
- DB: PostgreSQL (Render) o SQLite para pruebas locales.

## URLs principales
- API: `/docs` (Swagger)
- Scanner: `/scan` (requiere `?pin=SCANNER_PIN`)
- Endpoint validación: `/api/validate?token=...&trip_type=IDA&pickup_point=LA_COLONIA`

## Configuración (variables de entorno)
Ver `.env.example`.

**Importante (Render):**
- Setea `SCANNER_PIN` (secreto).
- Setea `PUBLIC_BASE_URL` con la URL pública del servicio API (ej: `https://ecobus-mvp-api.onrender.com`).

## Desarrollo local (rápido)
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
pip install -r requirements.txt

# API (usa SQLite local por defecto)
uvicorn app.main:app --reload

# Admin
streamlit run admin/admin_app.py
```

Scanner: abre `http://localhost:8000/scan?pin=1234`.

## Flujo operativo recomendado (MVP)
1) Crear pasajero (Admin > Pasajeros). Se genera token automáticamente.
2) Activar plan del mes (Admin > Planes mensuales) → se rota el token.
3) Descargar QR (PNG) con `POST /api/passengers/{id}/qr/regen` y reenviar por WhatsApp.
4) En operación, el pasajero encargado usa `/scan` y valida.

## Notas
- La validación aplica: token activo + ventana horaria + anti duplicado + plan pagado (o pase diario pagado/confirmado) + control de viajes incluidos.
- Si quieres **exportación Excel** además de CSV, se puede agregar rápido al Admin.
