import os
from datetime import datetime
import re
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from optimizador_pdf import optimizar_pdf
from sqlalchemy import func
from sqlalchemy import func, or_
from flask import send_from_directory
from dotenv import load_dotenv
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# Cargar las variables desde el archivo .env
load_dotenv()

app = Flask(__name__)

# Extraer las configuraciones del entorno de forma segura
app.secret_key = os.environ.get("SECRET_KEY", "clave_respaldo_por_defecto")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'pdfs'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

db = SQLAlchemy(app)

# --- CONFIGURACIÓN DE FLASK-LOGIN ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, inicie sesión para acceder al sistema."
login_manager.login_message_category = "error"


# --- NUEVOS MODELOS DE USUARIO Y AUDITORÍA ---
class Rol(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    cedula = db.Column(db.String(20), unique=True, nullable=False)
    telefono = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    activo = db.Column(db.Boolean, default=True)
    
    rel_rol = db.relationship('Rol')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Auditoria(db.Model):
    __tablename__ = 'auditoria'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    accion = db.Column(db.String(255), nullable=False)
    detalles = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(50), nullable=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    
    rel_usuario = db.relationship('Usuario')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))

# --- GENERACIÓN AUTOMÁTICA DE ROLES Y ADMIN POR DEFECTO ---
with app.app_context():
    db.create_all()
    
    # Crear roles si no existen
    roles_por_defecto = ['ADMINISTRADOR', 'ANALISTA', 'CONSULTA']
    for nombre_rol in roles_por_defecto:
        if not Rol.query.filter_by(nombre=nombre_rol).first():
            db.session.add(Rol(nombre=nombre_rol))
    db.session.commit()

    # Crear usuario administrador maestro si no existe
    if not Usuario.query.filter_by(username='admin').first():
        rol_admin = Rol.query.filter_by(nombre='ADMINISTRADOR').first()
        nuevo_admin = Usuario(
            username='admin', 
            rol_id=rol_admin.id,
            nombre='ADMINISTRADOR',
            apellido='SISTEMA',
            cedula='00000000',
            telefono='0000000000',
            email='admin@intu.gob.ve'
        )
        nuevo_admin.set_password('admin123') 
        db.session.add(nuevo_admin)
        db.session.commit()

# --- MODELOS DE LA BASE DE DATOS (DIVISION TERRITORIAL) ---

class Estado(db.Model):
    __tablename__ = 'estados'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    municipios = db.relationship('Municipio', backref='estado', lazy=True, cascade="all, delete-orphan")

class Municipio(db.Model):
    __tablename__ = 'municipios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    estado_id = db.Column(db.Integer, db.ForeignKey('estados.id'), nullable=False)
    parroquias = db.relationship('Parroquia', backref='municipio', lazy=True, cascade="all, delete-orphan")

class Parroquia(db.Model):
    __tablename__ = 'parroquias'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    municipio_id = db.Column(db.Integer, db.ForeignKey('municipios.id'), nullable=False)


# --- MODELOS DE REGISTRO DE TÍTULOS ---

class Titulo(db.Model):
    __tablename__ = 'titulos'
    id = db.Column(db.Integer, primary_key=True)
    
    # 1. Ubicación Geográfica
    estado_id = db.Column(db.Integer, db.ForeignKey('estados.id'), nullable=False)
    municipio_id = db.Column(db.Integer, db.ForeignKey('municipios.id'), nullable=False)
    parroquia_id = db.Column(db.Integer, db.ForeignKey('parroquias.id'), nullable=False)
    circuito_id = db.Column(db.Integer, db.ForeignKey('circuitos_comunales.id'), nullable=False)
    junta_id = db.Column(db.Integer, db.ForeignKey('juntas_comunales.id'), nullable=False)
    direccion_especifica = db.Column(db.Text, nullable=False)
    
    # 2. Linderos y Terreno
    lindero_norte = db.Column(db.String(255), nullable=False)
    lindero_sur = db.Column(db.String(255), nullable=False)
    lindero_este = db.Column(db.String(255), nullable=False)
    lindero_oeste = db.Column(db.String(255), nullable=False)
    medida_m2 = db.Column(db.Numeric(12, 2), nullable=False)
    medida_ha = db.Column(db.Numeric(12, 4), nullable=False) # 4 decimales estándar para hectáreas
    uso_actual_id = db.Column(db.Integer, db.ForeignKey('usos_actuales.id'), nullable=False)
    condicion_terreno = db.Column(db.String(50), nullable=False) # 'Público' o 'Privado'
    
    # 3. Datos Registrales
    nombre_registro = db.Column(db.String(255), nullable=False)
    numero_registro = db.Column(db.String(100), nullable=False)
    tomo = db.Column(db.String(50), nullable=False)
    protocolo = db.Column(db.String(50), nullable=False)
    folio = db.Column(db.String(50), nullable=False)
    fecha_protocolizacion = db.Column(db.Date, nullable=False)
    numero_asiento = db.Column(db.String(100), nullable=False)
    numero_matricula = db.Column(db.String(100), nullable=False)
    
    matriz_id = db.Column(db.Integer, db.ForeignKey('matrices_terreno.id'), nullable=False)
    medida_jur_id = db.Column(db.Integer, db.ForeignKey('medidas_juridicas.id'), nullable=False)
    origen_id = db.Column(db.Integer, db.ForeignKey('origenes_terreno.id'), nullable=False)
    cond_legal_reg_id = db.Column(db.Integer, db.ForeignKey('condiciones_legales_registrales.id'), nullable=False)
    numero_resolucion = db.Column(db.String(100), nullable=False)
    numero_gaceta = db.Column(db.String(100), nullable=False)
    numero_pagina = db.Column(db.String(50), nullable=False)
    estatus_id = db.Column(db.Integer, db.ForeignKey('estatus_registrales.id'), nullable=False)
    
    # Archivo físico
    ruta_archivo = db.Column(db.String(255), nullable=False)
    
    # Relaciones y Beneficiarios
    rel_estado = db.relationship('Estado')
    rel_municipio = db.relationship('Municipio')
    rel_parroquia = db.relationship('Parroquia')
    beneficiarios = db.relationship('Beneficiario', backref='titulo', lazy=True, cascade="all, delete-orphan")
    rel_circuito = db.relationship('CircuitoComunal')
    rel_junta = db.relationship('JuntaComunal')

class Beneficiario(db.Model):
    __tablename__ = 'beneficiarios'
    id = db.Column(db.Integer, primary_key=True)
    nombres = db.Column(db.String(150), nullable=False)
    apellidos = db.Column(db.String(150), nullable=False)
    cedula = db.Column(db.String(20), nullable=False)
    titulo_id = db.Column(db.Integer, db.ForeignKey('titulos.id'), nullable=False)

# --- NUEVAS TABLAS CATALÓGICAS ---
class CircuitoComunal(db.Model):
    __tablename__ = 'circuitos_comunales'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)

class JuntaComunal(db.Model):
    __tablename__ = 'juntas_comunales'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    parroquia_id = db.Column(db.Integer, db.ForeignKey('parroquias.id'), nullable=False)

class UsoActual(db.Model):
    __tablename__ = 'usos_actuales'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)

class MatrizTerreno(db.Model):
    __tablename__ = 'matrices_terreno'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)

class MedidaJuridica(db.Model):
    __tablename__ = 'medidas_juridicas'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)

class OrigenTerreno(db.Model):
    __tablename__ = 'origenes_terreno'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)

class CondicionLegalRegistral(db.Model):
    __tablename__ = 'condiciones_legales_registrales'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)

class EstatusRegistral(db.Model):
    __tablename__ = 'estatus_registrales'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)


# Crear las tablas dentro del contexto si no existen
with app.app_context():
    db.create_all()


# --- LÓGICA DE CONTROL DE ACCESO (RBAC) ---
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if current_user.rel_rol.nombre not in roles:
                flash('Acceso denegado: Su rol no tiene permisos para esta acción.', 'error')
                return redirect(request.referrer or url_for('estadisticas'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- LÓGICA DE AUDITORÍA AUTOMÁTICA ---
def registrar_auditoria(accion, detalles=""):
    usuario_id = current_user.id if current_user.is_authenticated else None
    ip = request.remote_addr
    log = Auditoria(usuario_id=usuario_id, accion=accion, detalles=detalles, ip=ip)
    db.session.add(log)
    db.session.commit()


# --- RUTAS DE LA APLICACIÓN ---




@app.route('/registro', methods=['GET', 'POST'])
@login_required
@role_required('ADMINISTRADOR', 'ANALISTA')
def registro():
    if request.method == 'POST':
        
        # ==========================================
        # 1. CAPTURA DE DATOS
        # ==========================================
        estado_id = request.form.get('estado')
        municipio_id = request.form.get('municipio')
        parroquia_id = request.form.get('parroquia')
        circuito_id = request.form.get('circuito_comunal')
        junta_id = request.form.get('junta_comunal') # Capturamos la junta
        fecha_prot_str = request.form.get('fecha_protocolizacion')
        
        # Captura y conversión a mayúsculas
        nombres = [n.upper().strip() for n in request.form.getlist('nombres[]')]
        apellidos = [a.upper().strip() for a in request.form.getlist('apellidos[]')]
        cedulas = [c.upper().strip() for c in request.form.getlist('cedulas[]')]

        beneficiarios_tuple = list(zip(nombres, apellidos, cedulas))
        beneficiarios_set = set((n, a, c) for n, a, c in beneficiarios_tuple)
        if len(beneficiarios_tuple) != len(beneficiarios_set):
            flash('Error: No se permiten beneficiarios duplicados en el mismo título.', 'registro_error')
            return redirect(request.url)

        # ==========================================
        # 2. VALIDACIÓN ESTRICTA (Ahora sí verificamos)
        # ==========================================
        
        # Validar campos generales de ubicación y fecha
        if not estado_id or not municipio_id or not parroquia_id or not circuito_id or not junta_id:
            flash('Error: Todos los campos de ubicación (incluyendo Circuito y Junta Comunal) son obligatorios. Si no aparecen juntas comunales, debe registrarlas primero en el sistema.', 'registro_error')
            return redirect(request.url)

        # Validar que las listas de beneficiarios no estén vacías
        if not nombres or not apellidos or not cedulas:
            flash('Error de seguridad: Debe registrar al menos un beneficiario completo.', 'registro_error')
            return redirect(request.url)

        # Validar que no haya campos de beneficiarios en blanco (solo espacios)
        if any(n == "" for n in nombres) or any(a == "" for a in apellidos) or any(c == "" for c in cedulas):
            flash('Error de seguridad: Ningún campo de los beneficiarios puede quedar en blanco.', 'registro_error')
            return redirect(request.url)
            
        # Validar que la fecha no sea futura
        fecha_obj = datetime.strptime(fecha_prot_str, '%Y-%m-%d')
        if fecha_obj.date() > datetime.now().date():
            flash('Error: La fecha de protocolización no puede ser mayor a la fecha actual.', 'registro_error')
            return redirect(request.url)

        # ==========================================
        # 3. PROCESAMIENTO DE ARCHIVOS Y BASE DE DATOS
        # ==========================================
        archivo_pdf = request.files.get('archivo_pdf')

        if not archivo_pdf or archivo_pdf.filename == '':
            flash('Debe cargar un archivo PDF válido.', 'registro_error')
            return redirect(request.url)

        entidad_estado = db.session.get(Estado, estado_id)
        if not entidad_estado:
            flash('Estado inválido o no seleccionado.', 'registro_error')
            return redirect(request.url)
            
        nombre_estado_slug = secure_filename(entidad_estado.nombre.lower())

        # 1. Determinar el año y estructurar directorios
        año = fecha_obj.strftime('%Y')
        carpeta_destino = os.path.join(app.config['UPLOAD_FOLDER'], nombre_estado_slug, año)
        os.makedirs(carpeta_destino, exist_ok=True)

        # 2. Construir la nomenclatura del archivo (la cédula ya está en mayúscula si tiene letras)
        cedula_principal_raw = cedulas[0] if cedulas else "SIN_CEDULA"
        cedula_principal = re.sub(r'[^a-zA-Z0-9-]', '', cedula_principal_raw)
        if not cedula_principal:
            cedula_principal = "SIN_CEDULA"
        fecha_formateada = fecha_obj.strftime('%Y%m%d')
        nombre_archivo = f"{nombre_estado_slug}_{cedula_principal}_{fecha_formateada}.pdf"
        ruta_final = os.path.join(carpeta_destino, nombre_archivo)
        
        # 3. Almacenamiento temporal y optimización
        ruta_temp = os.path.join(carpeta_destino, f"temp_{nombre_archivo}")
        archivo_pdf.save(ruta_temp)
        
        optimizado, warning = optimizar_pdf(ruta_temp, ruta_final)
        if optimizado:
            os.remove(ruta_temp)
        else:
            os.rename(ruta_temp, ruta_final)
            if warning:
                flash(f'Advertencia: {warning}', 'warning')

        
        # Captura de medidas y cálculo en backend por seguridad
        m2_str = request.form.get('medida_m2').replace(',', '.') # Por si el usuario usa coma decimal
        medida_m2_float = float(m2_str)
        medida_ha_float = medida_m2_float / 10000.0

        
        # 4. Inserción en PostgreSQL
        try:
            nuevo_titulo = Titulo(
                estado_id=estado_id, 
                municipio_id=municipio_id, 
                parroquia_id=parroquia_id, 
                circuito_id=request.form.get('circuito_comunal'),
                junta_id=request.form.get('junta_comunal'),
                direccion_especifica=request.form.get('direccion_especifica').upper(),
                
                lindero_norte=request.form.get('lindero_norte').upper(),
                lindero_sur=request.form.get('lindero_sur').upper(),
                lindero_este=request.form.get('lindero_este').upper(),
                lindero_oeste=request.form.get('lindero_oeste').upper(),
                medida_m2=medida_m2_float,
                medida_ha=medida_ha_float,
                uso_actual_id=request.form.get('uso_actual'),
                condicion_terreno=request.form.get('condicion_terreno'),
                
                nombre_registro=request.form.get('nombre_registro').upper(),
                numero_registro=request.form.get('numero_registro').upper(),
                tomo=request.form.get('tomo').upper(),
                protocolo=request.form.get('protocolo').upper(),
                folio=request.form.get('folio').upper(),
                fecha_protocolizacion=fecha_obj,
                numero_asiento=request.form.get('numero_asiento').upper(),
                numero_matricula=request.form.get('numero_matricula').upper(),
                
                matriz_id=request.form.get('matriz_perteneciente'),
                medida_jur_id=request.form.get('medida_juridica'),
                origen_id=request.form.get('origen_terreno'),
                cond_legal_reg_id=request.form.get('condicion_legal_registral'),
                numero_resolucion=request.form.get('numero_resolucion').upper(),
                numero_gaceta=request.form.get('numero_gaceta').upper(),
                numero_pagina=request.form.get('numero_pagina').upper(),
                estatus_id=request.form.get('estatus'),
                
                ruta_archivo=ruta_final
            )
            db.session.add(nuevo_titulo)
            db.session.flush()

            for n, a, c in zip(nombres, apellidos, cedulas):
                # Sanitización adicional por seguridad (asegura prefijo y números)
                cedula_limpia = c.replace(".", "").replace(" ", "").upper()
                nuevo_beneficiario = Beneficiario(nombres=n, apellidos=a, cedula=cedula_limpia, titulo_id=nuevo_titulo.id)
                db.session.add(nuevo_beneficiario)

            db.session.commit()
            registrar_auditoria("REGISTRO DE TÍTULO", f"Se registró el título con Cédula Principal: {cedula_principal}")
            flash('Título e historial de beneficiarios registrados y optimizados correctamente.', 'registro_success')
            
        except Exception as e:
            # Si ocurre cualquier error, deshacemos la transacción en la BD
            db.session.rollback()
            # Eliminamos el archivo PDF que se guardó temporalmente si la BD falla
            if os.path.exists(ruta_final):
                os.remove(ruta_final)
                
            flash(f'Error crítico al procesar los datos. Verifique que no haya incluido caracteres no permitidos. Detalles técnicos: {str(e)}', 'registro_error')
            
        return redirect(url_for('registro'))

    estados = Estado.query.order_by(Estado.nombre.asc()).all()
    circuitos = CircuitoComunal.query.order_by(CircuitoComunal.nombre.asc()).all()
    usos = UsoActual.query.order_by(UsoActual.nombre.asc()).all()
    matrices = MatrizTerreno.query.order_by(MatrizTerreno.nombre.asc()).all()
    medidas_jur = MedidaJuridica.query.order_by(MedidaJuridica.nombre.asc()).all()
    origenes = OrigenTerreno.query.order_by(OrigenTerreno.nombre.asc()).all()
    condiciones_reg = CondicionLegalRegistral.query.order_by(CondicionLegalRegistral.nombre.asc()).all()
    estatus_reg = EstatusRegistral.query.order_by(EstatusRegistral.nombre.asc()).all()
    
    fecha_actual = datetime.now().strftime('%Y-%m-%d')
    return render_template('index.html', estados=estados, fecha_actual=fecha_actual, 
                           circuitos=circuitos, usos=usos, matrices=matrices, 
                           medidas_jur=medidas_jur, origenes=origenes, 
                           condiciones_reg=condiciones_reg, estatus_reg=estatus_reg)


# --- ENDPOINTS REST PARA SELECTS DINÁMICOS (AJAX) ---

@app.route('/get_municipios/<int:estado_id>')
def get_municipios(estado_id):
    """Retorna los municipios asociados a un estado específico desde la BD."""
    municipios = Municipio.query.filter_by(estado_id=estado_id).order_by(Municipio.nombre.asc()).all()
    return jsonify([{"id": m.id, "nombre": m.nombre} for m in municipios])

@app.route('/get_parroquias/<int:municipio_id>')
def get_parroquias(municipio_id):
    """Retorna las parroquias asociadas a un municipio específico desde la BD."""
    parroquias = Parroquia.query.filter_by(municipio_id=municipio_id).order_by(Parroquia.nombre.asc()).all()
    return jsonify([{"id": p.id, "nombre": p.nombre} for p in parroquias])

@app.route('/get_juntas/<int:parroquia_id>')
def get_juntas(parroquia_id):
    juntas = JuntaComunal.query.filter_by(parroquia_id=parroquia_id).order_by(JuntaComunal.nombre.asc()).all()
    return jsonify([{"id": j.id, "nombre": j.nombre} for j in juntas])

# --- RUTA DE ESTADÍSTICAS Y BÚSQUEDA ---
@app.route('/estadisticas', methods=['GET'])
@login_required
@role_required('ADMINISTRADOR', 'CONSULTA')
def estadisticas():
    # 1. Estadísticas Generales (Lo que ya tienes)
    total_titulos = db.session.query(Titulo).count()

    desglose_estados = db.session.query(
        Estado.nombre, 
        func.count(Titulo.id).label('total_estado')
    ).join(Titulo, Estado.id == Titulo.estado_id)\
     .group_by(Estado.nombre)\
     .order_by(func.count(Titulo.id).desc()).all()

    # 2. Lógica del Buscador
    query_busqueda = request.args.get('q', '').strip()
    resultados_busqueda = []

    if query_busqueda:
        registrar_auditoria("BÚSQUEDA REALIZADA", f"Término buscado: {query_busqueda}")
        termino = f"%{query_busqueda}%"
        # Hacemos JOIN con Estado y Beneficiario para buscar en todas partes a la vez
        resultados_busqueda = Titulo.query.join(Estado).join(Beneficiario).filter(
            or_(
                Estado.nombre.ilike(termino),
                Beneficiario.cedula.ilike(termino),
                Beneficiario.nombres.ilike(termino),
                Beneficiario.apellidos.ilike(termino)
            )
        ).distinct().all() # distinct() evita que el título salga duplicado si coinciden varios beneficiarios

    return render_template(
        'estadisticas.html', 
        total=total_titulos, 
        desglose=desglose_estados,
        resultados=resultados_busqueda,
        query=query_busqueda
    )

# --- RUTA PARA VISUALIZAR EL PDF ---
@app.route('/ver_pdf/<int:titulo_id>')
def ver_pdf(titulo_id):
    titulo = db.session.get(Titulo, titulo_id)
    if not titulo:
        flash('El título solicitado no existe.', 'error')
        return redirect(url_for('estadisticas'))
    
    # Extraemos el directorio y el nombre del archivo de la ruta guardada
    directorio = os.path.dirname(titulo.ruta_archivo)
    nombre_archivo = os.path.basename(titulo.ruta_archivo)
    
    # send_from_directory es la forma segura de servir archivos en Flask
    return send_from_directory(directorio, nombre_archivo)

@app.errorhandler(413)
def too_large(e):
    flash('El archivo es demasiado grande. El tamaño máximo es 16 MB.', 'error')
    return redirect(request.url)

# --- RUTAS DE SESIÓN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('estadisticas'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        usuario = Usuario.query.filter_by(username=username).first()
        
        if usuario and usuario.check_password(password):
            if not usuario.activo:
                flash('Esta cuenta ha sido desactivada.', 'login_error')
                return redirect(url_for('login'))
                
            login_user(usuario)
            registrar_auditoria("INICIO DE SESIÓN", "El usuario accedió al sistema.")
            
            # Redirección inteligente según el rol
            if usuario.rel_rol.nombre in ['ANALISTA']:
                return redirect(url_for('registro'))
            else:
                return redirect(url_for('estadisticas'))
        else:
            registrar_auditoria("INTENTO FALLIDO", f"Intento de acceso con usuario: {username}")
            flash('Usuario o contraseña incorrectos.', 'login_error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    registrar_auditoria("CIERRE DE SESIÓN", "El usuario salió del sistema.")
    logout_user()
    return redirect(url_for('login'))

# --- ADMINISTRACIÓN DE USUARIOS (Solo Administrador) ---
@app.route('/usuarios', methods=['GET', 'POST'])
@login_required
@role_required('ADMINISTRADOR')
def gestion_usuarios():
    query_busqueda = request.args.get('q', '')
    if query_busqueda:
        usuarios = Usuario.query.filter(Usuario.username.ilike(f'%{query_busqueda}%')).all()
    else:
        usuarios = Usuario.query.all()
    
    if request.method == 'POST':
        # CAPTURA TODOS LOS NUEVOS CAMPOS DEL FORMULARIO
        username = request.form.get('username')
        password = request.form.get('password')
        rol_id = request.form.get('rol_id')
        nombre = request.form.get('nombre')
        apellido = request.form.get('apellido')
        cedula = request.form.get('cedula')
        telefono = request.form.get('telefono')
        email = request.form.get('email')

        # Verificación de usuario existente
        if Usuario.query.filter((Usuario.username == username) | (Usuario.email == email)).first():
            flash('Error: El usuario o correo ya existen.', 'usuarios_error')
        else:
            # CREACIÓN DEL USUARIO CON TODOS LOS DATOS
            nuevo_usuario = Usuario(
                username=username, 
                rol_id=rol_id,
                nombre=nombre.upper(),
                apellido=apellido.upper(),
                cedula=cedula.upper(),
                telefono=telefono,
                email=email.lower()
            )
            nuevo_usuario.set_password(password)
            db.session.add(nuevo_usuario)
            db.session.commit()
            registrar_auditoria("CREACIÓN DE USUARIO", f"Se creó el usuario: {username}")
            flash('Usuario creado exitosamente.', 'usuarios_success')
        return redirect(url_for('gestion_usuarios'))

    usuarios = Usuario.query.all()
    roles = Rol.query.all()
    return render_template('usuarios.html', usuarios=usuarios, roles=roles)

@app.route('/usuarios/editar/<int:id>', methods=['POST'])
@login_required
@role_required('ADMINISTRADOR')
def editar_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    
    # Capturar todos los campos del formulario
    usuario.username = request.form.get('username')
    usuario.nombre = request.form.get('nombre').upper()
    usuario.apellido = request.form.get('apellido').upper()
    usuario.cedula = request.form.get('cedula').upper()
    usuario.telefono = request.form.get('telefono')
    usuario.email = request.form.get('email').lower()
    usuario.rol_id = int(request.form.get('rol_id'))
    usuario.activo = request.form.get('activo') == 'true'  # Ahora recibe 'true' o 'false'
    
    # Si se proporcionó una nueva contraseña, actualizarla
    nueva_password = request.form.get('password')
    if nueva_password and nueva_password.strip():
        usuario.set_password(nueva_password)
    
    db.session.commit()
    
    registrar_auditoria("EDICIÓN DE USUARIO", f"Usuario {usuario.username} actualizado")
    
    flash('Usuario actualizado correctamente.', 'usuarios_success')
    return redirect(url_for('gestion_usuarios'))

@app.route('/usuarios/obtener/<int:id>', methods=['GET'])
@login_required
@role_required('ADMINISTRADOR')
def obtener_usuario(id):
    """Retorna los datos de un usuario en formato JSON para editar en modal"""
    usuario = Usuario.query.get_or_404(id)
    return jsonify({
        'id': usuario.id,
        'username': usuario.username,
        'nombre': usuario.nombre,
        'apellido': usuario.apellido,
        'cedula': usuario.cedula,
        'telefono': usuario.telefono,
        'email': usuario.email,
        'rol_id': usuario.rol_id,
        'activo': usuario.activo
    })


# --- VISOR DE AUDITORÍA (Solo Administrador) ---
@app.route('/auditoria')
@login_required
@role_required('ADMINISTRADOR')
def ver_auditoria():
    # Capturar parámetros
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    username_filtro = request.args.get('usuario')
    accion = request.args.get('accion')

    # Iniciamos el query haciendo JOIN con la tabla Usuario
    query = db.session.query(Auditoria).join(Usuario, Auditoria.usuario_id == Usuario.id)

    # Filtros
    if fecha_inicio:
        query = query.filter(func.date(Auditoria.fecha) >= datetime.strptime(fecha_inicio, '%Y-%m-%d').date())
    if fecha_fin:
        query = query.filter(func.date(Auditoria.fecha) <= datetime.strptime(fecha_fin, '%Y-%m-%d').date())
    if username_filtro:
        query = query.filter(Usuario.username.ilike(f'%{username_filtro}%'))
    if accion:
        query = query.filter(Auditoria.accion == accion)

    # Agregar después de los filtros:
    page = request.args.get('page', 1, type=int)
    per_page = 50
    pagination = query.order_by(Auditoria.fecha.desc()).paginate(page=page, per_page=per_page, error_out=False)
    registros = pagination.items
    
    # Obtener acciones únicas para el desplegable
    acciones_disponibles = db.session.query(Auditoria.accion).distinct().all()

    return render_template('auditoria.html', 
                           logs=registros, 
                           pagination=pagination,  # ← IMPORTANTE: esto debe estar
                           acciones=acciones_disponibles)


if __name__ == '__main__':
    app.run(debug=True, port=5000)