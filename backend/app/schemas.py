from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nombre_completo: str
    rol: Optional[str] = "COLABORADOR"

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    nombre_completo: str
    rol: str
    activo: bool
    class Config:
        from_attributes = True

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    rol: str
    nombre_completo: str
    email: str

class ModuloCreate(BaseModel):
    nombre: str

class RegistroPruebaCreate(BaseModel):
    modulo_id: int
    sector_nombre: str
    proceso_nombre: str
    empleado_asignado_id: int
    fase: str
    resultado_estado: str
    fecha_inicio: Optional[datetime.datetime] = None
    fecha_fin: Optional[datetime.datetime] = None
    observacion_error: Optional[str] = None
    enviado_a: Optional[str] = None
    fecha_envio: Optional[datetime.datetime] = None
    devolucion_tango: Optional[str] = None

    @field_validator('fecha_inicio', 'fecha_fin', 'fecha_envio', mode='before')
    @classmethod
    def parse_empty_string_dates(cls, value):
        if value == "" or value is None:
            return None
        return value

class CompletarTareaSchema(BaseModel):
    resultado_estado: str  # "Aprobado" o "Fallido"
    fecha_fin: Optional[datetime.datetime] = None
    observacion_error: Optional[str] = None
    enviado_a: Optional[str] = None
    devolucion_tango: Optional[str] = None

    @field_validator('fecha_fin', mode='before')
    @classmethod
    def parse_empty_string_dates(cls, value):
        if value == "" or value is None:
            return None
        return value