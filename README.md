# Sistema de Registro de Títulos de Tierras Urbanas

Este proyecto es una aplicación web desarrollada en Python con el framework Flask, diseñada para la digitalización, registro y consulta eficiente de títulos de tierras urbanas. El sistema permite registrar la ubicación geográfica, múltiples beneficiarios asociados a un mismo título y optimizar automáticamente los documentos PDF escaneados para ahorrar espacio de almacenamiento en el servidor.

---

## 🚀 Características Principales

* **Registro Relacional:** Formulario dinámico con selectores en cascada (Estado > Municipio > Parroquia) consultados directamente desde la base de datos.
* **Gestión Dinámica de Beneficiarios:** Capacidad de agregar uno o múltiples beneficiarios (Nombres, Apellidos y Cédula) por cada título protocolizado.
* **Optimización de Archivos:** Integración nativa con Ghostscript para reducir drásticamente el peso de los documentos PDF cargados sin perder legibilidad.
* **Almacenamiento Estructurado:** Los archivos se guardan siguiendo la nomenclatura estandarizada `estado_cedula_ddmmaaaa.pdf` y se organizan en carpetas físicas estructuradas por `estado/año`.
* **Panel de Control Estadístico:** Visualización en tiempo real del total de títulos registrados y su desglose por estado geográfico.
* **Buscador Integral:** Motor de búsqueda que permite localizar títulos filtrando simultáneamente por estado, nombre, apellido o cédula de identidad, con previsualización directa del documento PDF.

---

## 🛠️ Arquitectura y Stack Tecnológico

* **Backend:** Python 3, Flask.
* **Base de Datos:** PostgreSQL (Motor principal) y SQLAlchemy (ORM para modelado e interacción relacional).
* **Procesamiento de Archivos:** Werkzeug (manejo seguro de rutas) y Ghostscript (compresión de PDF).
* **Frontend:** HTML5, CSS3 (Diseño modular tipo *Bento Box*, responsive), JavaScript (Fetch API para consultas AJAX).
* **Seguridad:** Gestión de credenciales mediante variables de entorno (`python-dotenv`).

---

## ⚙️ Requisitos Previos (Servidor Linux)

Antes de instalar la aplicación, el servidor (Debian/Ubuntu) debe contar con los siguientes paquetes del sistema operativo:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip postgresql postgresql-contrib libpq-dev ghostscript nginx

```

---

## 📦 Instalación y Configuración

### 1. Clonar y preparar el entorno

Posiciónate en el directorio donde alojarás la aplicación (ej. `/var/www/`) y prepara el entorno virtual:

```bash
cd /var/www/
# Clonar o mover la carpeta del proyecto aquí
cd sistema_titulos

# Crear y activar el entorno virtual
python3 -m venv venv
source venv/bin/activate

```

### 2. Instalar dependencias de Python

Con el entorno virtual activado, instala los paquetes requeridos:

```bash
pip install -r requirements.txt
pip install gunicorn # Necesario para el despliegue en producción

```

### 3. Configuración de Base de Datos

Accede a la consola de PostgreSQL para crear la base de datos y el usuario:

```bash
sudo -u postgres psql

```

```sql
CREATE DATABASE bd_titulos;
CREATE USER mi_usuario WITH PASSWORD 'mi_contraseña_segura';
ALTER ROLE mi_usuario SET client_encoding TO 'utf8';
ALTER ROLE mi_usuario SET default_transaction_isolation TO 'read committed';
ALTER ROLE mi_usuario SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE bd_titulos TO mi_usuario;
\q

```

### 4. Variables de Entorno

Crea el archivo `.env` en la raíz del proyecto para definir tus credenciales:

```bash
nano .env

```

Contenido del `.env`:

```env
SECRET_KEY=tu_clave_secreta_aleatoria
DATABASE_URL=postgresql://mi_usuario:mi_contraseña_segura@localhost:5432/bd_titulos

```

### 5. Carga Inicial de Datos (Seed)

Una vez configurado el `.env`, ejecuta la aplicación una vez para que SQLAlchemy construya las tablas, y luego inyecta la división territorial (ej. Estado Miranda):

*Nota: Ejecuta tu script SQL en la base de datos o el script de Python diseñado para la carga inicial de estados, municipios y parroquias.*

---

## 🌐 Despliegue en Producción (Gunicorn + Systemd + Nginx)

Para entornos de producción, no se debe utilizar el servidor de desarrollo de Flask. Utilizaremos **Gunicorn** gestionado por **Systemd**, detrás de un proxy inverso con **Nginx**.

### 1. Crear el servicio de Systemd

```bash
sudo nano /etc/systemd/system/titulos.service

```

Añade la siguiente configuración (ajusta las rutas según tu servidor):

```ini
[Unit]
Description=Instancia Gunicorn para el Sistema de Títulos
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/sistema_titulos
Environment="PATH=/var/www/sistema_titulos/venv/bin"
# Lee las variables de entorno
EnvironmentFile=/var/www/sistema_titulos/.env
ExecStart=/var/www/sistema_titulos/venv/bin/gunicorn --workers 3 --bind unix:sistema_titulos.sock -m 007 app:app

[Install]
WantedBy=multi-user.target

```

Inicia y habilita el servicio:

```bash
sudo systemctl start titulos
sudo systemctl enable titulos

```

### 2. Configurar Nginx como Proxy Inverso

Crea el bloque de servidor en Nginx:

```bash
sudo nano /etc/nginx/sites-available/titulos

```

Añade la configuración:

```nginx
server {
    listen 80;
    server_name tu_dominio_o_IP;

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/sistema_titulos/sistema_titulos.sock;
    }

    # Optimización para servir los PDF y estáticos directamente con Nginx
    location /pdfs {
        alias /var/www/sistema_titulos/pdfs;
    }
}

```

Habilita el sitio y reinicia Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/titulos /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx

```

El sistema estará ahora en línea y listo para su uso institucional.

```

```
