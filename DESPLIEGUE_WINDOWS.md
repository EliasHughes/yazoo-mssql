# YLMS — Guía de Despliegue Local en Windows (Prototipo Yazoo)

> Objetivo: correr YLMS en una **PC/portátil Windows 10/11** para la demo del prototipo,
> con SQL Server local (opcional) o SQLite (por defecto para el prototipo). Sin nubes,
> sin dominio, sin certificados. Todo en `localhost`.

---

## 1. Requisitos previos (30 minutos)

Instalar en orden:

1. **Python 3.11 (x64)** — https://www.python.org/downloads/windows/
   - Marcar **"Add python.exe to PATH"** en el instalador.
   - Verificar en `cmd`: `python --version` → `Python 3.11.x`
2. **Node.js 20 LTS** — https://nodejs.org/en/download
   - Verificar: `node -v` → `v20.x`
3. **Yarn**: en `cmd` como administrador ejecutar `npm install -g yarn`
4. **Git para Windows** — https://git-scm.com/download/win
5. *(Opcional para producción)* **SQL Server 2019+ Express o Developer**
   - Descargar de https://www.microsoft.com/es-es/sql-server/sql-server-downloads
   - Instalar con **Autenticación mixta** (crear usuario `ylms` con contraseña).
   - Instalar **ODBC Driver 18 for SQL Server**:
     https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server

> **Para el prototipo/demo NO es obligatorio SQL Server.** El sistema arranca en **SQLite**
> (archivo `ylms_local.db` en la carpeta backend) y todo funciona igual.

---

## 2. Copiar el código

Opción A — Clonar de GitHub (si ya usaste "Save to GitHub" desde Emergent):
```cmd
cd C:\
git clone https://github.com/TU-USUARIO/ylms.git YLMS
cd YLMS
```

Opción B — Copiar la carpeta `/app` completa desde Emergent (Download ZIP) y
descomprimir en `C:\YLMS`.

Estructura esperada:
```
C:\YLMS\
 ├─ backend\      (FastAPI + SQLAlchemy)
 ├─ frontend\     (React 19 + Tailwind)
 ├─ memory\       (PRD, credenciales)
 └─ DESPLIEGUE_WINDOWS.md   (este archivo)
```

---

## 3. Configurar el Backend

Abrir `cmd` en `C:\YLMS\backend`.

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3.1 Archivo `.env` (backend)

Crear `C:\YLMS\backend\.env` con este contenido:

```
# --- Base de datos (elegir UNA) ---
# Opción A: SQLite (recomendado para demo)
DATABASE_URL=sqlite+aiosqlite:///./ylms_local.db

# Opción B: SQL Server local (descomentar si tienes SQL Server instalado)
# DATABASE_URL=mssql+aioodbc://ylms:TuPassword@localhost:1433/YLMS_DB?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes

MONGO_URL=sqlite+aiosqlite:///./ylms_local.db
DB_NAME=ylms

# --- Auth ---
JWT_SECRET=cambia-esta-cadena-larga-y-secreta-para-produccion
BCRYPT_ROUNDS=12

# --- Semilla de admin ---
ADMIN_EMAIL=admin@yazoo.com
ADMIN_PASSWORD=Admin123!

# --- Emergent LLM (opcional, deja vacío en demo) ---
EMERGENT_LLM_KEY=

# --- Correo (opcional para envío real de volantes) ---
RESEND_API_KEY=
```

### 3.2 Si eligiste SQL Server, crear la base

```sql
CREATE DATABASE YLMS_DB;
GO
CREATE LOGIN ylms WITH PASSWORD = 'TuPassword';
USE YLMS_DB;
CREATE USER ylms FOR LOGIN ylms;
ALTER ROLE db_owner ADD MEMBER ylms;
GO
```
Las tablas se crean automáticamente al primer arranque (SQLAlchemy `create_all`).

### 3.3 Probar el backend

```cmd
cd C:\YLMS\backend
.venv\Scripts\activate
uvicorn server:app --host 0.0.0.0 --port 8001
```

Abrir http://localhost:8001/api/health → debe responder `{"status":"ok"}`.

---

## 4. Configurar el Frontend

Abrir otra ventana `cmd` en `C:\YLMS\frontend`.

### 4.1 Archivo `.env` (frontend)

Crear `C:\YLMS\frontend\.env` con:

```
REACT_APP_BACKEND_URL=http://localhost:8001
WDS_SOCKET_PORT=3000
```

### 4.2 Instalar y arrancar

```cmd
cd C:\YLMS\frontend
yarn install
yarn start
```

El navegador abrirá automáticamente http://localhost:3000.

Credenciales:
- Email: `admin@yazoo.com`
- Contraseña: `Admin123!`

---

## 5. Correr como servicio de Windows (opcional)

Para que YLMS arranque solo con Windows, usar **NSSM** (Non-Sucking Service Manager):

1. Descargar NSSM: https://nssm.cc/download → copiar `nssm.exe` a `C:\YLMS\`.
2. Registrar servicio backend:
   ```cmd
   nssm install YLMS-Backend
   ```
   - **Path**: `C:\YLMS\backend\.venv\Scripts\python.exe`
   - **Startup directory**: `C:\YLMS\backend`
   - **Arguments**: `-m uvicorn server:app --host 0.0.0.0 --port 8001`
3. Registrar servicio frontend (build de producción):
   ```cmd
   cd C:\YLMS\frontend
   yarn build
   npm install -g serve
   nssm install YLMS-Frontend
   ```
   - **Path**: `C:\Program Files\nodejs\node.exe`
   - **Startup directory**: `C:\YLMS\frontend`
   - **Arguments**: `C:\Users\%USERNAME%\AppData\Roaming\npm\node_modules\serve\bin\serve.js -s build -l 3000`

Iniciar servicios:
```cmd
nssm start YLMS-Backend
nssm start YLMS-Frontend
```

---

## 6. Acceso desde otras PCs de la LAN (opcional)

1. Sacar la IP del servidor: `ipconfig` → `IPv4` (ej. `192.168.1.50`).
2. En `frontend\.env` cambiar a:
   ```
   REACT_APP_BACKEND_URL=http://192.168.1.50:8001
   ```
3. Rebuild: `yarn build` y reiniciar `YLMS-Frontend`.
4. Abrir puertos 3000 y 8001 en el Firewall de Windows:
   ```cmd
   netsh advfirewall firewall add rule name="YLMS-Web"  dir=in action=allow protocol=TCP localport=3000
   netsh advfirewall firewall add rule name="YLMS-API"  dir=in action=allow protocol=TCP localport=8001
   ```
5. Otras PCs entran a `http://192.168.1.50:3000`.

---

## 7. Backup y restauración

### SQLite (default demo)
Copiar el archivo `C:\YLMS\backend\ylms_local.db` a un pendrive/OneDrive. Punto.

### SQL Server
```sql
BACKUP DATABASE YLMS_DB TO DISK = 'C:\Backups\YLMS_DB.bak' WITH INIT;
```
Programar en el **Agente SQL Server** una tarea diaria.

---

## 8. Solución de problemas frecuentes

| Problema | Causa | Solución |
|----------|-------|----------|
| `uvicorn` no arranca — "ModuleNotFoundError" | venv sin activar | `.venv\Scripts\activate` |
| Frontend muestra "Network Error" | backend caído o URL mal | Verificar `REACT_APP_BACKEND_URL` y que `http://localhost:8001/api/health` responde |
| Login rechaza credenciales | Semilla no corrió | Borrar `ylms_local.db` y reiniciar backend (recrea el admin) |
| SQL Server: "Login failed" | Usuario `ylms` sin permisos | Ejecutar los `GRANT` del paso 3.2 |
| Puerto 3000/8001 ocupado | Otra app | `netstat -ano \| findstr :8001` → matar PID |

---

## 9. Créditos de demo (test_credentials.md)

Ver `C:\YLMS\memory\test_credentials.md`. Por defecto:

- **Administrador**: `admin@yazoo.com` / `Admin123!`
- Otros roles se crean desde **Sistema → Usuarios** una vez logueado como admin.

---

## 10. Checklist rápido para la demo

- [ ] Backend arranca en http://localhost:8001/api/health
- [ ] Frontend arranca en http://localhost:3000
- [ ] Login con admin funciona
- [ ] Puedo crear un empleado (RRHH → Empleados)
- [ ] Puedo calcular nómina del mes actual (Nómina → Calcular)
- [ ] Puedo generar una cotización PDF con QR (Ventas → Cotizaciones → Descargar PDF)
- [ ] Sidebar se pliega automáticamente al entrar a un módulo
- [ ] EHS: puedo registrar un incidente y una inspección
- [ ] Inventario: Kardex muestra movimientos con saldo corrido

> Si algún ítem falla, revisa **Sección 8** o los logs del backend en la consola donde
> corrió `uvicorn`.

---

**Yazoo Rones y Bebidas del Caribe · YLMS v2.0 · Feb 2026**
