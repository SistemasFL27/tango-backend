import os
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Si existe la variable DATABASE_URL en Render usa PostgreSQL, de lo contrario SQLite local
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tango.db")

# Ajuste de compatibilidad para SQLAlchemy en Render
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# FUNCIÓN PARA MIGRAR HISTORIAL DESDE SQLITE A POSTGRESQL SIN PERDER DATOS
def migrar_datos_desde_sqlite_si_aplica():
    sqlite_path = "./tango.db"
    if "sqlite" not in DATABASE_URL and os.path.exists(sqlite_path):
        try:
            print("📦 Detectada base de datos SQLite anterior. Iniciando comprobación de migración a PostgreSQL...")
            conn_sqlite = sqlite3.connect(sqlite_path)
            cursor = conn_sqlite.cursor()

            db_pg = SessionLocal()
            from app.models import DBUser, DBModulo, DBProceso, DBEjecucionPrueba, DBHistorialDetalle, DBAdjunto

            # 1. Migrar Usuarios
            try:
                cursor.execute("SELECT id, email, password_hash, nombre_completo, rol, activo FROM usuarios")
                for u in cursor.fetchall():
                    u_id, u_email, u_hash, u_nombre, u_rol, u_activo = u
                    email_clean = u_email.strip().lower()
                    if not db_pg.query(DBUser).filter(DBUser.email == email_clean).first():
                        db_pg.add(DBUser(id=u_id, email=email_clean, password_hash=u_hash, nombre_completo=u_nombre, rol=u_rol, activo=bool(u_activo)))
                db_pg.commit()
            except Exception as e:
                db_pg.rollback()
                print(f"Nota migración usuarios: {e}")

            # 2. Migrar Módulos
            try:
                cursor.execute("SELECT id, nombre FROM modulos")
                for m in cursor.fetchall():
                    m_id, m_nombre = m
                    if not db_pg.query(DBModulo).filter(DBModulo.id == m_id).first():
                        db_pg.add(DBModulo(id=m_id, nombre=m_nombre))
                db_pg.commit()
            except Exception as e:
                db_pg.rollback()

            db_pg.close()
            conn_sqlite.close()
            print("✅ Comprobación de migración completada con éxito.")
        except Exception as err:
            print(f"⚠️ Aviso en proceso de migración: {err}")