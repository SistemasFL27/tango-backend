import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from app.database import Base

class DBUser(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    nombre_completo = Column(String, nullable=False)
    rol = Column(String, default="COLABORADOR")  # "ADMIN" o "COLABORADOR"
    activo = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=datetime.datetime.utcnow)

class DBModulo(Base):
    __tablename__ = "modulos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, nullable=False)

class DBProceso(Base):
    __tablename__ = "procesos"

    id = Column(Integer, primary_key=True, index=True)
    modulo_id = Column(Integer, ForeignKey("modulos.id"), nullable=False)
    nombre = Column(String, nullable=False)
    descripcion_ruta = Column(String, nullable=True)

class DBEjecucionPrueba(Base):
    __tablename__ = "ejecuciones_prueba"

    id = Column(Integer, primary_key=True, index=True)
    proceso_id = Column(Integer, ForeignKey("procesos.id"), nullable=False)
    sector_nombre = Column(String, nullable=False)
    empleado_asignado_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fase = Column(String, default="Prueba")
    estado_actual = Column(String, default="En curso")
    fecha_inicio = Column(DateTime, default=datetime.datetime.utcnow)
    fecha_fin = Column(DateTime, nullable=True)
    numero_intento_actual = Column(Integer, default=1)

class DBHistorialDetalle(Base):
    __tablename__ = "historial_detalle"

    id = Column(Integer, primary_key=True, index=True)
    ejecucion_prueba_id = Column(Integer, ForeignKey("ejecuciones_prueba.id"), nullable=False)
    numero_intento = Column(Integer, nullable=False)
    probado_por_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    observacion_error = Column(Text, nullable=True)
    enviado_a = Column(String, nullable=True)
    fecha_envio = Column(DateTime, nullable=True)
    devolucion_tango = Column(Text, nullable=True)
    resultado_estado = Column(String, nullable=False)
    fecha_registro = Column(DateTime, default=datetime.datetime.utcnow)

class DBAdjunto(Base):
    __tablename__ = "adjuntos"

    id = Column(Integer, primary_key=True, index=True)
    historial_id = Column(Integer, ForeignKey("historial_detalle.id"), nullable=False)
    nombre_archivo = Column(String, nullable=False)
    ruta_archivo = Column(String, nullable=False)

class DBAuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    usuario_email = Column(String, nullable=False)
    usuario_nombre = Column(String, nullable=False)
    accion = Column(String, nullable=False)
    detalle = Column(Text, nullable=False)
    fecha = Column(DateTime, default=datetime.datetime.utcnow)