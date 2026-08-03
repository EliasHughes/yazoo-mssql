# YLMS Test Credentials

## Admin
- **Email**: admin@yazoo.com
- **Password**: Admin123!

## Data layer
- Preview: SQLite (`/app/backend/ylms_local.db`)
- Producción: MSSQL 2019 vía `DATABASE_URL=mssql+aioodbc://ylms_app:PWD@localhost:1433/ylms_prod?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes&Encrypt=yes`

## Endpoints nuevos (Fase A parcial)
- GET /api/system/currencies · PUT (admin)
- GET /api/system/next-code?prefix=PRD  → `{code: "PRD-00003", seq: 3}`
- Existentes: /api/auth, /api/users, /api/signatures/*, /api/search/*, /api/notifications, /api/inventory/*, /api/lab-forms/*, /api/attachments/*, /api/exports/*, /api/coa/{id}/pdf?format=modern|standard

## Roles
admin, quality_manager, supervisor, analyst, microbiologist, chemist, auxiliary, production, warehouse, auditor, management.
