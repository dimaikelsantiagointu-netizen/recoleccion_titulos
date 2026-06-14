# crear_indices.py - Ejecutar una sola vez
from app import app, db
from sqlalchemy import text

with app.app_context():
    indices = [
        "CREATE INDEX IF NOT EXISTS idx_beneficiario_cedula ON beneficiarios(cedula);",
        "CREATE INDEX IF NOT EXISTS idx_beneficiario_nombres ON beneficiarios(nombres);",
        "CREATE INDEX IF NOT EXISTS idx_beneficiario_apellidos ON beneficiarios(apellidos);",
        "CREATE INDEX IF NOT EXISTS idx_titulo_estado ON titulos(estado_id);",
        "CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria(fecha);"
    ]
    
    for idx in indices:
        try:
            db.session.execute(text(idx))
            print(f"✅ Índice creado: {idx[:50]}...")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    db.session.commit()
    print("✅ Todos los índices fueron procesados.")