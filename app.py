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


# --- RUTAS DE LA APLICACIÓN ---

@app.route('/', methods=['GET', 'POST'])
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

        # ==========================================
        # 2. VALIDACIÓN ESTRICTA (Ahora sí verificamos)
        # ==========================================
        
        # Validar campos generales de ubicación y fecha
        if not estado_id or not municipio_id or not parroquia_id or not circuito_id or not junta_id:
            flash('Error: Todos los campos de ubicación (incluyendo Circuito y Junta Comunal) son obligatorios. Si no aparecen juntas comunales, debe registrarlas primero en el sistema.', 'error')
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
            flash('Título e historial de beneficiarios registrados y optimizados correctamente.', 'success')
            
        except Exception as e:
            # Si ocurre cualquier error, deshacemos la transacción en la BD
            db.session.rollback()
            # Eliminamos el archivo PDF que se guardó temporalmente si la BD falla
            if os.path.exists(ruta_final):
                os.remove(ruta_final)
                
            flash(f'Error crítico al procesar los datos. Verifique que no haya incluido caracteres no permitidos. Detalles técnicos: {str(e)}', 'error')
            
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