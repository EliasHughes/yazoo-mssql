# YLMS · PRD (Ago 2026)

Stack: FastAPI + SQLAlchemy async (SQLite dev / MSSQL prod) + React 19 + Tailwind + ReportLab + openpyxl + qrcode.

## Iter 16 · 03-Ago-2026 (pre-demo Yazoo - continuación)

### 🔴 Bugs P0 corregidos (demo mañana)
- **CRÍTICO: Pérdida de datos al editar registros de laboratorio.** El endpoint `GET /lab-forms/records` excluía el campo `data` de la lista (proyección `{"data": 0}`). Al hacer clic en "Editar", el frontend pasaba `initial.data = undefined` y `initFromSchema` devolvía un formulario vacío. **Solución:** función `openEdit()` en `LabFormPage.js` que hace `GET /lab-forms/records/{id}` para obtener el registro completo antes de abrir el modal. Los datos guardados ahora se preservan al editar.
- **Formularios nuevos invisibles como tiles.** `lf_water` y `lf_aged_distilled` faltaban en `SCREEN_TO_MODULE` de `Workspace.js`. Agregados → aparecen en Workspace → Registros de Laboratorio.
- **Botón Eliminar removido en registros de laboratorio.** Política Yazoo: los datos del ERP no se borran. El botón se reemplaza con toast informativo "Solicita anulación al administrador".

### 💱 Moneda y ITBIS
- Monedas soportadas: **DOP, USD, EUR** en Compras, Ventas, CxP, CxC, Órdenes.
- **IVA → ITBIS** en toda la UI y comentarios de código (18%).
- Backend `erp_purchases.py`: default `currency="DOP"` y `tax_rate=0.18`.

### 🟢 Submódulos nuevos (Iter 16)
- **Inventario → Transferencias entre Almacenes** (`/inventory/transfers`)
  - Flujo Pendiente → Aprobada → Completada con trazabilidad en `stock_movements`
  - No se permite origen=destino, no se pueden cancelar completadas
- **Inventario → Tanques y Silos** (`/inventory/tanks`)
  - CRUD con capacidad_L, volumen_actual_L, % llenado calculado
  - Actualizar volumen con validación de capacidad y log en `stock_movements`
  - Tipos: Almacenamiento / Fermentación / Envejecimiento / Mezcla
  - Vista tipo tarjetas con barra de llenado (verde <70%, amarillo 70-90%, rojo >90%)
- **Inventario → Cuarentena / Bloqueo de Lotes** (`/inventory/quarantine`)
  - Retención de lotes con estado (quarantined → released / rejected)
  - Actualiza `quarantine_status` en `batches` para bloquear despacho
- **Producción → Recetas / Fórmulas (BOM)** (`/production/recipes`)
  - CRUD con versionado (`new-version` archiva la anterior)
  - Cálculo automático de costo total y costo unitario
  - **MRP básico**: explosión de componentes por cantidad objetivo
- **RRHH → Vacaciones y Permisos** (`/hr/vacations`)
  - Solicitudes con cálculo automático de días
  - Aprobación/Rechazo, KPIs por estado
- **RRHH → Organigrama** (`/hr/organigram`)
  - Vista jerárquica plegable basada en `manager_id`
  - Asignar/quitar manager desde la UI

### 🔧 Backend nuevos routers
- `/app/backend/routers/inventory_ops.py` — transferencias, tanques, cuarentena
- `/app/backend/routers/recipes.py` — recetas + MRP
- `/app/backend/routers/hr_ext.py` — vacaciones + organigrama
- `/app/backend/db.py` — 4 colecciones nuevas: `tanks`, `batch_quarantines`, `vacations` (+ `inventory_transfers`, `recipes` de Iter 15)
- `/app/backend/screens.py` — 7 screens nuevas: `inv_transfers`, `inv_tanks`, `inv_quarantine`, `prod_recipes`, `hr_vacations`, `hr_organigram`, `sales_orders`, `finance_ap`, `finance_ar`

### 🖥️ Frontend nuevas páginas
- `InventoryTransfers.js`, `InventoryTanks.js`, `InventoryQuarantine.js`
- `Recipes.js` (con modal MRP)
- `HRVacations.js`, `HROrganigram.js` (flatten iterativo, sin recursión de componente)

### ✅ Tests
- `test_iter16_bugfixes_and_submodules.py` (6 tests):
  - `test_edit_endpoint_returns_full_data` (verifica bugfix crítico)
  - `test_inventory_transfer_flow` (create → approve → complete)
  - `test_tank_capacity_and_fill` (fill_pct auto-calculado)
  - `test_batch_quarantine_and_release`
  - `test_recipe_with_versioned_bom`
  - `test_vacation_request_flow` (create + approve)
- **Suite iter11..iter16: 32/32 PASS**

## Iter 15 · 03-Ago-2026 (pre-demo Yazoo)

### 🔴 Bloqueadores P0 resueltos
- **Frontend en blanco por temporal-dead-zone en `schemas.js`**: `ALL_SCHEMAS` referenciaba `waterAnalysisSchema` y `agedDistilledControlSchema` antes de ser declaradas. Se movió el registro maestro al final del archivo.
- **Test `test_new_form_types_registered` fallando**: el endpoint `/api/lab-forms/types` devuelve lista, no dict. Se corrigió el test para iterar el arreglo.

### 📝 Cambios del PDF `cambio-082026.pdf` (formularios)
- **Aging Process (Y-FO-CO-001)** — parametros ahora incluye Operador, Aspecto, Olor, Sabor, Analista, Observación como filas por etapa.
- **Prueba Triangular (Y-FO-CC-007)** — rediseño: Trío 1 y Trío 2 con selector A/B/C independiente + grado de confianza (Muy seguro/Seguro/Poco seguro). Autofirma del panelista en "nombre" y "cata_preparada_por". Se removieron firmas por rol y campo "muestra vinculada".
- **Sesiones Catado (Y-FO-CC-008)** — sin firmas por rol, sin muestras vinculadas, `verificado_por` autofirmado por usuario.
- **Recepción Granel (Y-FO-CC-011)** — agregado campo Mes y tabla vertical Parámetro / Especificación / Resultado. Decisión Aprobado/Rechazado + firma calidad proveedor.
- **Control de Envasado (Y-FO-CC-034)** — tabla ARRANQUE DE LINEA con 8 filas por hora (grado/capacidad/color/nm/dureza/turbidez/viscosidad/fuga/catado/pto llenado) + trazabilidad de lote separada.

### 🟢 Submódulos nuevos Alta Prioridad
- **Finanzas → Cuentas por Pagar** (`/finance/ap`)
  - CRUD facturas de proveedor (NCF, emitida, vence, subtotal, ITBIS, total, moneda, notas)
  - Registro de pagos parciales con actualización de saldo y estado (pending → partial → paid)
  - Reporte de antigüedad (aging) con buckets 0-30 / 31-60 / 61-90 / >90 días
- **Finanzas → Cuentas por Cobrar** (`/finance/ar`)
  - Extiende `sales_invoices` con cobros aplicados (`ar_payments`)
  - Muestra Cobrado / Saldo calculados en línea
  - Reporte de antigüedad idéntico a CxP
- **Ventas → Órdenes de Venta** (`/sales/orders`)
  - Flujo Borrador → Confirmada → Despachada → Facturada (transiciones validadas)
  - Al facturar auto-crea `sales_invoices` con estado `issued`
  - KPIs por estado + valor abierto

### 🔧 Backend
- `/app/backend/routers/finance_ap_ar.py` (nuevo) — routers `/finance/ap` y `/finance/ar` con aging y pagos
- `/app/backend/routers/sales_orders.py` (nuevo) — router `/sales/orders` con máquina de estados
- `/app/backend/db.py` — nuevas colecciones: `ap_invoices`, `ap_payments`, `ar_payments`, `sales_orders`, `inventory_transfers`, `recipes`
- `/app/backend/screens.py` — 3 nuevas screens: `finance_ap`, `finance_ar`, `sales_orders`
- `/app/backend/routers/lab_forms.py` — `triangular_test` y `tasting_session` con `signature_slots: []` + autofill panelista

### 🖥️ Frontend
- `/app/frontend/src/pages/FinanceAP.js`, `FinanceAR.js`, `SalesOrders.js` (nuevos)
- `/app/frontend/src/pages/labforms/schemas.js` — 5 schemas rediseñados + soporte `hideLinkedSample`
- `/app/frontend/src/pages/labforms/LabFormPage.js` — respeta `hideLinkedSample`, autofirma amplida a `nombre`, `cata_preparada_por`, `preparada_por`, `panelista`
- `/app/frontend/src/App.js` — 3 rutas nuevas
- `/app/frontend/src/components/Layout.js` — MODULE_SCREENS extendido
- `/app/frontend/src/pages/Workspace.js` — SCREEN_ICON / SCREEN_TO_ROUTE / SCREEN_TO_MODULE actualizados

### ✅ Tests
- `test_iter15_pdf_form_changes.py` (3 tests) — sin firmas rol tasting/triangular, autofirma panelista, bulk_reception acepta `mes`
- `test_iter15_submodules.py` (3 tests) — flujo CxP completo con aging, órdenes de venta con state machine y factura auto-creada, aplicación de cobros CxC
- **Suite iter11..iter15: 26 tests PASS**

## Iter 14 · Ago 2026
- Formularios nuevos Y-FO-CC-012 (Análisis Agua) y Y-FO-CC-009 (Envejecidos y Destilados).

## Iter 13 · Feb 2026
- EHS extendido: Incidentes/Casi-accidentes, EPP, Inspecciones, `/ehs/dashboard`.
- Inventario extendido: Kardex, Conteo físico con ajustes automáticos.

## Iter 12 · Feb 2026
- Sidebar plegable, botón Volver, BUG 500 empleado, QR en PDF, auto-códigos, aprobación de compras.

## Iter 11 y previos
Sidebar 15 módulos Dynamics 365, Cotización PDF bilingüe, Mantenimiento Calendario, Logística, I+D, Workspace, Nómina RD 2026, EHS Accidentes, Firmas, CoA bilingüe.

## Pendientes post-demo (backlog priorizado)
1. **Inventario → Transferencias entre Almacenes** (colección `inventory_transfers` ya creada; UI pendiente)
2. **Producción → Recetas / Fórmulas** (colección `recipes` ya creada; UI pendiente)
3. Producción → MRP básico (explosión BOM)
4. RRHH → Organigrama visual + Vacaciones y Permisos
5. Compras → RFQ multi-proveedor
6. I+D extendido: Fichas Experimentación, Análisis Sensorial, QC Inicial
7. Seguridad Industrial: MSDS, Capacitaciones SST, Permisos de trabajo, Incidentes ambientales
8. Endurecer Modo Offline: revisar `bcryptjs` en `AuthContext.js`

## Credenciales
`admin@yazoo.com` / `Admin123!`. Ver `/app/memory/test_credentials.md`.

## Despliegue local (para la demo de mañana)
Ver **`/app/DESPLIEGUE_WINDOWS.md`**.
