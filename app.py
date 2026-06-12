import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from optimizador_pdf import optimizar_pdf
from sqlalchemy import func
from sqlalchemy import func, or_
from flask import send_from_directory
from dotenv import load_dotenv

# Cargar las variables desde el archivo .env
load_dotenv()

app = Flask(__name__)

# Extraer las configuraciones del entorno de forma segura
app.secret_key = os.environ.get("SECRET_KEY", "clave_respaldo_por_defecto")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'pdfs'

db = SQLAlchemy(app)

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
    
    # Relaciones relacionales con la división territorial
    estado_id = db.Column(db.Integer, db.ForeignKey('estados.id'), nullable=False)
    municipio_id = db.Column(db.Integer, db.ForeignKey('municipios.id'), nullable=False)
    parroquia_id = db.Column(db.Integer, db.ForeignKey('parroquias.id'), nullable=False)
    
    fecha_protocolizacion = db.Column(db.Date, nullable=False)
    ruta_archivo = db.Column(db.String(255), nullable=False)
    
    # Relaciones para consultas rápidas
    rel_estado = db.relationship('Estado')
    rel_municipio = db.relationship('Municipio')
    rel_parroquia = db.relationship('Parroquia')
    beneficiarios = db.relationship('Beneficiario', backref='titulo', lazy=True, cascade="all, delete-orphan")

class Beneficiario(db.Model):
    __tablename__ = 'beneficiarios'
    id = db.Column(db.Integer, primary_key=True)
    nombres = db.Column(db.String(150), nullable=False)
    apellidos = db.Column(db.String(150), nullable=False)
    cedula = db.Column(db.String(20), nullable=False)
    titulo_id = db.Column(db.Integer, db.ForeignKey('titulos.id'), nullable=False)


# Crear las tablas dentro del contexto si no existen
with app.app_context():
    db.create_all()


# --- RUTAS DE LA APLICACIÓN ---

@app.route('/', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        
        # ==========================================
        # 1. CAPTURA DE DATOS (Primero extraemos todo)
        # ==========================================
        estado_id = request.form.get('estado')
        municipio_id = request.form.get('municipio')
        parroquia_id = request.form.get('parroquia')
        fecha_prot_str = request.form.get('fecha_protocolizacion')
        
        # Captura y conversión a mayúsculas
        nombres = [n.upper().strip() for n in request.form.getlist('nombres[]')]
        apellidos = [a.upper().strip() for a in request.form.getlist('apellidos[]')]
        cedulas = [c.upper().strip() for c in request.form.getlist('cedulas[]')]

        # ==========================================
        # 2. VALIDACIÓN ESTRICTA (Ahora sí verificamos)
        # ==========================================
        
        # Validar campos generales de ubicación y fecha
        if not estado_id or not municipio_id or not parroquia_id or not fecha_prot_str:
            flash('Error de seguridad: Todos los campos de ubicación y fecha son obligatorios.', 'error')
            return redirect(request.url)

        # Validar que las listas de beneficiarios no estén vacías
        if not nombres or not apellidos or not cedulas:
            flash('Error de seguridad: Debe registrar al menos un beneficiario completo.', 'error')
            return redirect(request.url)

        # Validar que no haya campos de beneficiarios en blanco (solo espacios)
        if any(n == "" for n in nombres) or any(a == "" for a in apellidos) or any(c == "" for c in cedulas):
            flash('Error de seguridad: Ningún campo de los beneficiarios puede quedar en blanco.', 'error')
            return redirect(request.url)
            
        # Validar que la fecha no sea futura
        fecha_obj = datetime.strptime(fecha_prot_str, '%Y-%m-%d')
        if fecha_obj.date() > datetime.now().date():
            flash('Error: La fecha de protocolización no puede ser mayor a la fecha actual.', 'error')
            return redirect(request.url)

        # ==========================================
        # 3. PROCESAMIENTO DE ARCHIVOS Y BASE DE DATOS
        # ==========================================
        archivo_pdf = request.files.get('archivo_pdf')

        if not archivo_pdf or archivo_pdf.filename == '':
            flash('Debe cargar un archivo PDF válido.', 'error')
            return redirect(request.url)

        entidad_estado = db.session.get(Estado, estado_id)
        if not entidad_estado:
            flash('Estado inválido o no seleccionado.', 'error')
            return redirect(request.url)
            
        nombre_estado_slug = secure_filename(entidad_estado.nombre.lower())

        # 1. Determinar el año y estructurar directorios
        año = fecha_obj.strftime('%Y')
        carpeta_destino = os.path.join(app.config['UPLOAD_FOLDER'], nombre_estado_slug, año)
        os.makedirs(carpeta_destino, exist_ok=True)

        # 2. Construir la nomenclatura del archivo (la cédula ya está en mayúscula si tiene letras)
        cedula_principal = secure_filename(cedulas[0]) if cedulas else "SIN_CEDULA"
        fecha_formateada = fecha_obj.strftime('%Y%m%d')
        nombre_archivo = f"{nombre_estado_slug}_{cedula_principal}_{fecha_formateada}.pdf"
        ruta_final = os.path.join(carpeta_destino, nombre_archivo)
        
        # 3. Almacenamiento temporal y optimización
        ruta_temp = os.path.join(carpeta_destino, f"temp_{nombre_archivo}")
        archivo_pdf.save(ruta_temp)
        
        if optimizar_pdf(ruta_temp, ruta_final):
            os.remove(ruta_temp)
        else:
            os.rename(ruta_temp, ruta_final)

        # 4. Inserción en PostgreSQL
        nuevo_titulo = Titulo(
            estado_id=estado_id, 
            municipio_id=municipio_id, 
            parroquia_id=parroquia_id, 
            fecha_protocolizacion=fecha_obj,
            ruta_archivo=ruta_final
        )
        db.session.add(nuevo_titulo)
        db.session.flush()

        for n, a, c in zip(nombres, apellidos, cedulas):
            nuevo_beneficiario = Beneficiario(nombres=n, apellidos=a, cedula=c, titulo_id=nuevo_titulo.id)
            db.session.add(nuevo_beneficiario)

        db.session.commit()
        flash('Título e historial de beneficiarios registrados y optimizados correctamente.', 'success')
        return redirect(url_for('registro'))

    estados = Estado.query.order_by(Estado.nombre.asc()).all()
    # Pasamos la fecha actual al template para bloquear fechas futuras en el calendario HTML
    fecha_actual = datetime.now().strftime('%Y-%m-%d')
    return render_template('index.html', estados=estados, fecha_actual=fecha_actual)


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


# --- RUTA DE ESTADÍSTICAS Y BÚSQUEDA ---
@app.route('/estadisticas', methods=['GET'])
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


if __name__ == '__main__':
    app.run(debug=True, port=5000)