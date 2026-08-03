# YLMS · Guía de Despliegue en Windows Server 2019 con MSSQL + IIS

Documento oficial para poner **YLMS (Yazoo Laboratory Management System)** en
producción sobre el servidor interno de Rones y Bebidas del Caribe Yazoo.

**Requisitos previos que asume esta guía:**
- Un servidor Windows Server 2019 en la fábrica.
- Sólo servicio ISP local, **sin infraestructura corporativa**.
- **25 usuarios concurrentes**.
- Acceso remoto **multidispositivo** (laptops, tablets, celulares) por **VPN**.
- Base de datos **Microsoft SQL Server 2019+** (Express o Standard).
- Backend Python/FastAPI expuesto por **IIS** vía `web.config` con URL Rewrite +
  Application Request Routing (ARR) como reverse-proxy.
- Backend corriendo como **servicio Windows con NSSM**.
- Firewall exclusivamente sobre red interna + segmento VPN.

---

## 1. Especificaciones mínimas del servidor

| Componente             | Mínimo                | Recomendado (25 usuarios)    |
|------------------------|-----------------------|------------------------------|
| CPU                    | 4 vCPU / 4 núcleos    | 8 vCPU / 8 núcleos           |
| RAM                    | 16 GB                 | 32 GB                        |
| Disco SO               | SSD 200 GB            | SSD 250 GB                   |
| Disco datos (MSSQL + uploads) | 500 GB SSD     | 1 TB SSD + RAID-1            |
| SO                     | Windows Server 2019   | Windows Server 2019 Standard |
| Uplink ISP             | 20 Mbps simétricos    | 50 Mbps simétricos + IP fija |
| UPS                    | 30 min                | 60 min + generador           |

---

## 2. Componentes a instalar

| # | Componente                                        | Uso                              |
|---|---------------------------------------------------|----------------------------------|
| 1 | **Microsoft SQL Server 2019+** (Express o Standard) | Base de datos                    |
| 2 | **SQL Server Management Studio (SSMS)**           | Administración                   |
| 3 | **Microsoft ODBC Driver 18 for SQL Server**       | Cliente ODBC para el backend     |
| 4 | **Python 3.11 x64**                               | Runtime backend                  |
| 5 | **Node.js LTS 20+**                               | Build del frontend               |
| 6 | **Git for Windows**                               | Deploy y actualizaciones         |
| 7 | **IIS + URL Rewrite + Application Request Routing (ARR)** | Reverse proxy                    |
| 8 | **NSSM** (Non-Sucking Service Manager)            | Servicio Windows para el backend |
| 9 | **WireGuard for Windows**                         | VPN corporativa                  |
| 10| **7-Zip**                                         | Respaldos                        |

---

## 3. Instalación paso a paso

### 3.1. Microsoft SQL Server 2019+

1. Descarga desde https://www.microsoft.com/sql-server/sql-server-downloads
   (SQL Server 2019 Express Edition es suficiente para 25 usuarios y hasta 10 GB
   de datos por base; para mayor tamaño usa Standard).
2. Ejecuta el instalador → **Instalación básica**.
3. Selecciona modo mixto (SQL + Windows Authentication):
   - Contraseña de `sa`: `<SA_PASSWORD_FUERTE>`
4. Descarga **SSMS**: https://aka.ms/ssmsfullsetup
5. Instala **ODBC Driver 18**: https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server
6. Habilita **TCP/IP** (SQL Server Configuration Manager → SQL Server Network Configuration → TCP/IP → Enabled, puerto 1433 loopback).
7. Reinicia el servicio `MSSQLSERVER` o `SQLEXPRESS`.

### 3.2. Crear base de datos y usuario de aplicación

En SSMS:

```sql
CREATE DATABASE ylms_prod
  COLLATE Latin1_General_100_CI_AI_SC_UTF8;
GO

CREATE LOGIN ylms_app WITH PASSWORD = '<APP_PASSWORD_FUERTE>',
    CHECK_POLICY = ON;
GO

USE ylms_prod;
GO

CREATE USER ylms_app FOR LOGIN ylms_app;
ALTER ROLE db_datareader ADD MEMBER ylms_app;
ALTER ROLE db_datawriter ADD MEMBER ylms_app;
ALTER ROLE db_ddladmin  ADD MEMBER ylms_app;   -- necesario para auto-crear tablas/índices
GO
```

> El backend crea automáticamente las tablas, los índices NONCLUSTERED, los
> procedimientos almacenados (`sp_next_seq`) y los triggers de auditoría al
> iniciar por primera vez (ver `db.py::init_database`).

### 3.3. Backend

```powershell
cd C:\
mkdir ylms; cd ylms
git clone https://github.com/<tu-repo>/ylms.git app
cd app\backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Editar `C:\ylms\app\backend\.env`:

```
DATABASE_URL=mssql+aioodbc://ylms_app:<APP_PASSWORD_FUERTE>@localhost:1433/ylms_prod?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes&Encrypt=yes
JWT_SECRET=<HASH_ALEATORIO_64_CHARS>
ADMIN_EMAIL=admin@yazoo.com
ADMIN_PASSWORD=<CONTRASEÑA_INICIAL>
CORS_ORIGINS=https://ylms.yazoo.local,http://ylms.yazoo.local
YLMS_UPLOADS_DIR=D:\ylms\uploads
YLMS_SIGNATURES_DIR=D:\ylms\signatures
YLMS_MAX_UPLOAD_MB=15
```

Prueba manual (una vez):

```powershell
python -m uvicorn server:app --host 0.0.0.0 --port 8001
```

Deberías ver en logs:
- `Seeded admin user: admin@yazoo.com`
- `Application startup complete.`

### 3.4. Backend como servicio Windows con NSSM

```powershell
nssm install YLMSBackend "C:\ylms\app\backend\.venv\Scripts\python.exe" ^
  "-m" "uvicorn" "server:app" "--host" "127.0.0.1" "--port" "8001" "--workers" "2"
nssm set YLMSBackend AppDirectory C:\ylms\app\backend
nssm set YLMSBackend AppStdout C:\ylms\logs\backend-out.log
nssm set YLMSBackend AppStderr C:\ylms\logs\backend-err.log
nssm set YLMSBackend AppRotateFiles 1
nssm set YLMSBackend AppRotateBytes 10485760
nssm set YLMSBackend Start SERVICE_AUTO_START
nssm start YLMSBackend
```

Verifica:

```powershell
curl http://127.0.0.1:8001/api/health
```

### 3.5. Frontend

Editar `C:\ylms\app\frontend\.env`:

```
REACT_APP_BACKEND_URL=https://ylms.yazoo.local
```

Compilar y desplegar a IIS:

```powershell
cd C:\ylms\app\frontend
yarn install --frozen-lockfile
yarn build
xcopy /E /I /Y build C:\inetpub\wwwroot\ylms
```

### 3.6. IIS como reverse-proxy (web.config)

1. Instala IIS con: URL Rewrite + Application Request Routing (ARR).
2. En IIS Manager → Server → **Application Request Routing Cache** → Server Proxy Settings → **Enable Proxy**.
3. Crea un sitio **YLMS** apuntando a `C:\inetpub\wwwroot\ylms` en puerto 443 con binding HTTPS.
4. Copia el siguiente `web.config` a la raíz del sitio:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <!-- API: proxy hacia el backend FastAPI en localhost:8001 -->
        <rule name="ReverseProxyToFastAPI" stopProcessing="true">
          <match url="^api/(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8001/api/{R:1}" />
          <serverVariables>
            <set name="HTTP_X_FORWARDED_FOR" value="{REMOTE_ADDR}" />
            <set name="HTTP_X_FORWARDED_PROTO" value="{HTTPS,https,http}" />
            <set name="HTTP_X_FORWARDED_HOST" value="{HTTP_HOST}" />
          </serverVariables>
        </rule>

        <!-- SPA: cualquier ruta no-archivo devuelve index.html -->
        <rule name="ReactRouterFallback" stopProcessing="true">
          <match url=".*" />
          <conditions logicalGrouping="MatchAll">
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
            <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
          </conditions>
          <action type="Rewrite" url="/index.html" />
        </rule>
      </rules>
    </rewrite>

    <staticContent>
      <clientCache cacheControlMode="UseMaxAge" cacheControlMaxAge="7.00:00:00" />
      <mimeMap fileExtension=".webp" mimeType="image/webp" />
      <mimeMap fileExtension=".woff2" mimeType="font/woff2" />
    </staticContent>

    <httpProtocol>
      <customHeaders>
        <add name="X-Content-Type-Options" value="nosniff" />
        <add name="X-Frame-Options" value="SAMEORIGIN" />
        <add name="Referrer-Policy" value="strict-origin-when-cross-origin" />
      </customHeaders>
    </httpProtocol>

    <security>
      <requestFiltering>
        <requestLimits maxAllowedContentLength="20971520" />
        <!-- 20 MB para subir firmas y evidencias -->
      </requestFiltering>
    </security>

    <!-- IMPORTANTE: permitir rewrite de servervariables -->
    <httpErrors errorMode="Detailed" />
  </system.webServer>

  <!-- Habilitar las server variables usadas en el proxy -->
  <location path="." inheritInChildApplications="false">
    <system.webServer>
      <rewrite>
        <allowedServerVariables>
          <add name="HTTP_X_FORWARDED_FOR" />
          <add name="HTTP_X_FORWARDED_PROTO" />
          <add name="HTTP_X_FORWARDED_HOST" />
        </allowedServerVariables>
      </rewrite>
    </system.webServer>
  </location>
</configuration>
```

5. Aumenta el request timeout del proxy en `applicationHost.config` (opcional, exports pesados):
   - IIS Manager → Configuration Editor → `system.webServer/proxy` → `timeout` = `00:05:00`.

### 3.7. Certificado HTTPS

Autofirmado (bueno para LAN + VPN):

```powershell
New-SelfSignedCertificate -DnsName "ylms.yazoo.local" -CertStoreLocation "cert:\LocalMachine\My" -FriendlyName "YLMS Yazoo"
```

Bindea el certificado en IIS al puerto 443 del sitio YLMS.
Distribúyelo por GPO / manual a las PCs cliente (Certificados de Autoridad Raíz de Confianza).

---

## 4. Red interna + VPN multidispositivo

### 4.1. LAN interna
- Servidor con IP fija `192.168.10.10`.
- Añadir a las PCs cliente (o al DNS del router):
  `192.168.10.10  ylms.yazoo.local`

### 4.2. VPN (WireGuard) para tablets/celulares/laptops externos

Como sólo hay ISP local, **la VPN corre en el propio servidor**.

1. Instala WireGuard for Windows → https://www.wireguard.com/install/
2. Crea la interfaz `wg0`:
   - Red: `10.20.0.0/24`
   - Puerto UDP: `51820`
   - Clave pública/privada generada por WireGuard
3. En el router ISP: **port-forward UDP 51820 → 192.168.10.10:51820**.
4. Para cada dispositivo (celular / tablet / laptop):
   - Genera un peer con IP única `10.20.0.x`
   - QR code para importar en la app WireGuard móvil (Android/iOS)
   - `.conf` para escritorio
   - `AllowedIPs = 192.168.10.0/24, 10.20.0.0/24`
5. En cada cliente, apunta al servidor por su nombre: `ylms.yazoo.local`.

**Recomendación:** limita la VPN a gerencia/dirección/auditoría; analistas y almacén trabajan sólo desde LAN.

---

## 5. Firewall (Windows Defender) — reglas estrictas

Ejecuta en PowerShell **como administrador**:

```powershell
# Bloquea todo inbound por defecto
Set-NetFirewallProfile -Profile Domain,Public,Private -DefaultInboundAction Block -DefaultOutboundAction Allow

# HTTPS interno (LAN + VPN)
New-NetFirewallRule -DisplayName "YLMS HTTPS LAN" -Direction Inbound -Protocol TCP -LocalPort 443 `
  -RemoteAddress 192.168.10.0/24,10.20.0.0/24 -Action Allow -Profile Domain,Private

# WireGuard VPN (UDP)
New-NetFirewallRule -DisplayName "YLMS WireGuard" -Direction Inbound -Protocol UDP -LocalPort 51820 -Action Allow

# NUNCA expuestos a Internet directo:
# - SQL Server (1433)
# - Backend (8001)
# Solo bind a loopback / interna.
New-NetFirewallRule -DisplayName "MSSQL Solo Loopback" -Direction Inbound -Protocol TCP -LocalPort 1433 `
  -RemoteAddress 127.0.0.1,192.168.10.0/24 -Action Allow -Profile Domain,Private
Get-NetFirewallRule | Where-Object DisplayName -like "*SQL Server*" | Where-Object { $_.DisplayName -ne "MSSQL Solo Loopback" } | Set-NetFirewallRule -Enabled False
```

---

## 6. Respaldos automáticos MSSQL

Archivo `C:\ylms\backup.ps1`:

```powershell
$today = Get-Date -Format "yyyyMMdd_HHmm"
$dest  = "D:\ylms\backups"
if (-not (Test-Path $dest)) { New-Item -ItemType Directory -Path $dest | Out-Null }

# Backup de la base
Invoke-Sqlcmd -ServerInstance "localhost" -Query "
  BACKUP DATABASE ylms_prod TO DISK = N'$dest\ylms_prod_$today.bak' WITH INIT, COMPRESSION, STATS = 10;"

# Copia uploads y firmas
Compress-Archive -Path D:\ylms\uploads,D:\ylms\signatures -DestinationPath "$dest\assets_$today.zip"

# Retención 30 días
Get-ChildItem $dest | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item -Recurse -Force
```

Programa en el **Programador de Tareas** cada día a las **02:00 AM**.

Restaurar en emergencia:

```sql
RESTORE DATABASE ylms_prod FROM DISK = N'D:\ylms\backups\ylms_prod_20260228_0200.bak' WITH REPLACE, STATS = 10;
```

---

## 7. Migración de datos desde MongoDB (una sola vez)

Si vienes de una instancia previa MongoDB, ejecuta el script incluido:

```powershell
cd C:\ylms\app\backend
.venv\Scripts\Activate.ps1
python -m tools.migrate_mongo_to_sql --mongo-url "mongodb://user:pass@host:27017" --mongo-db "ylms_prod"
```

El script (`backend/tools/migrate_mongo_to_sql.py` — a incluir en el próximo build)
copia todas las colecciones al MSSQL respetando los IDs originales.

---

## 8. Checklist pre-producción (viernes)

- [ ] `MSSQLSERVER` (o `SQLEXPRESS`) corriendo
- [ ] Base `ylms_prod` creada con collation UTF-8
- [ ] Usuario `ylms_app` con permisos `datareader`, `datawriter`, `ddladmin`
- [ ] ODBC Driver 18 instalado
- [ ] `YLMSBackend` (NSSM) corriendo → `curl http://127.0.0.1:8001/api/health` = OK
- [ ] IIS con URL Rewrite + ARR + web.config
- [ ] Certificado HTTPS instalado y bindeado a `ylms.yazoo.local:443`
- [ ] `https://ylms.yazoo.local` responde y login `admin@yazoo.com / <ADMIN_PASSWORD>` funciona
- [ ] WireGuard corriendo, un dispositivo remoto puede conectarse
- [ ] Firewall bloquea inbound salvo `443` y `51820`
- [ ] Task Scheduler ejecuta `backup.ps1` a las 02:00 AM
- [ ] Task Scheduler ejecuta `curl -X POST http://127.0.0.1:8001/api/inventory/alerts/scan -H "Authorization: Bearer <SERVICE_TOKEN>"` cada 4 h (opcional)

---

## 9. Actualización del sistema

```powershell
Stop-Service YLMSBackend
cd C:\ylms\app
git pull
cd backend
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Start-Service YLMSBackend

cd ..\frontend
yarn install --frozen-lockfile
yarn build
xcopy /E /I /Y build C:\inetpub\wwwroot\ylms
iisreset
```

---

## 10. Recuperación ante fallos de MongoDB (histórico)

Los fallos anteriores con MongoDB en producción **quedan resueltos por esta
migración**. YLMS ahora:
- Usa **transacciones ACID** de MSSQL nativas.
- Almacena imágenes/PDFs en **disco** con referencia en tabla (no como blobs).
- Aplica **índices NONCLUSTERED** en las columnas indexadas críticas.
- Ejecuta **triggers de auditoría** que replican INSERT/UPDATE/DELETE al log.
- **Stored procedures** para operaciones críticas (`sp_next_seq`, respaldos).
- **Compresión y respaldos** automáticos de la base.

Cualquier duda técnica queda registrada en `Auditoría` para trazabilidad.
