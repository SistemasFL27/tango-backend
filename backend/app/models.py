import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class DBUser(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    nombre_completo = Column(String, nullable=False)
    rol = Column(String, default="COLABORADOR")
    activo = Column(Boolean, default=True)

class DBModulo(Base):
    __tablename__ = "modulos_tango"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, nullable=False)

class DBProceso(Base):
    __tablename__ = "procesos_tango"
    id = Column(Integer, primary_key=True, index=True)
    modulo_id = Column(Integer, ForeignKey("modulos_tango.id"), nullable=False)
    nombre = Column(String, nullable=False)
    descripcion_ruta = Column(String, nullable=True)

class DBEjecucionPrueba(Base):
    __tablename__ = "ejecuciones_prueba"
    id = Column(Integer, primary_key=True, index=True)
    proceso_id = Column(Integer, ForeignKey("procesos_tango.id"), nullable=False)
    sector_nombre = Column(String, nullable=False)
    empleado_asignado_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    fase = Column(String, nullable=False)
    estado_actual = Column(String, default="En curso")
    fecha_inicio = Column(DateTime, default=datetime.datetime.utcnow)
    fecha_fin = Column(DateTime, nullable=True)
    numero_intento_actual = Column(Integer, default=1)

class DBHistorialDetalle(Base):
    __tablename__ = "detalle_historial_pruebas"
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
    
    # Relación con adjuntos
    adjuntos = relationship("DBAdjunto", back_populates="historial", cascade="all, delete-orphan")

class DBAdjunto(Base):
    __tablename__ = "adjuntos_prueba"
    id = Column(Integer, primary_key=True, index=True)
    historial_id = Column(Integer, ForeignKey("detalle_historial_pruebas.id"), nullable=False)
    nombre_archivo = Column(String, nullable=False)
    ruta_archivo = Column(String, nullable=False)
    creado_en = Column(DateTime, default=datetime.datetime.utcnow)

    historial = relationship("DBHistorialDetalle", back_populates="adjuntos")