import os
import shutil
import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db, migrar_datos_desde_sqlite_si_aplica
from app.models import DBUser, DBModulo, DBProceso, DBEjecucionPrueba, DBHistorialDetalle, DBAdjunto, DBAuditLog
from app.schemas import UserCreate, UserResponse, LoginResponse, ModuloCreate
from app.auth import hash_password, verify_password, create_access_token, get_current_user, require_admin

# Inicialización de Tablas de BD
Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title="Sistema de Pruebas Tango ERP - Enterprise Production V9", 
    version="9.0.0"
)

# Middleware CORS para acceso desde cPanel / dominios cruzados
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=200)
    else:
        response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ==============================================================================
# LISTA MAESTRA DE USUARIOS RAÍZ (SEED DATA)
# ==============================================================================
USUARIOS_PREDEFINIDOS = [
    # Administradores
    {"nombre": "Sistemas Flecha Log", "email": "sistemas@flechalog.com", "pass": "Admin2626!@", "rol": "ADMIN"},
    {"nombre": "Néstor Dova", "email": "ndova@flechalog.com", "pass": "Ndov1-", "rol": "ADMIN"},
    {"nombre": "Roxana Rosales", "email": "rrosales@flechalog.com", "pass": "Rros8-", "rol": "ADMIN"},
    {"nombre": "Soraya Bartolozzi", "email": "sbartolozzi@flechalog.com", "pass": "Sbart-6", "rol": "ADMIN"},
    {"nombre": "Belen Barbieri", "email": "bbarbieri@flechalog.com", "pass": "Bbarb-14", "rol": "ADMIN"},
    {"nombre": "Rodolfo Martinez", "email": "rmartinez@flechalog.com", "pass": "Rmart-80", "rol": "ADMIN"},
    {"nombre": "Gladys Coello", "email": "gcoello@flechainternationalgroup.com", "pass": "Gcoell-74", "rol": "ADMIN"},
    {"nombre": "Diego Bartolozzi", "email": "dbartolozzi@flechalog.com", "pass": "Dbart-58", "rol": "ADMIN"},
    {"nombre": "Antonio Fedele", "email": "afedele@flechalog.com", "pass": "Afede-88", "rol": "ADMIN"},
    # Colaboradores
    {"nombre": "Diego Bartolozzi (Colaborador Prueba)", "email": "dbartolozzi_test@flechalog.com", "pass": "Diego123", "rol": "COLABORADOR"},
    {"nombre": "Celeste Iberra", "email": "ciberra@flechalog.com", "pass": "Cib-5983", "rol": "COLABORADOR"}
]

def poblar_usuarios_maestros(db: Session):
    for u in USUARIOS_PREDEFINIDOS:
        email_clean = u["email"].strip().lower()
        user_db = db.query(DBUser).filter(DBUser.email == email_clean).first()
        
        if not user_db:
            nuevo = DBUser(
                email=email_clean,
                password_hash=hash_password(u["pass"]),
                nombre_completo=u["nombre"],
                rol=u["rol"],
                activo=True
            )
            db.add(nuevo)
        else:
            # Actualizar contraseña y asegurar activación
            user_db.password_hash = hash_password(u["pass"])
            user_db.nombre_completo = u["nombre"]
            user_db.rol = u["rol"]
            user_db.activo = True
            
    db.commit()
    print("✅ Todos los usuarios predefinidos han sido verificados/sincronizados.")

def registrar_auditoria(db: Session, usuario: DBUser, accion: str, detalle: str):
    try:
        log = DBAuditLog(
            usuario_email=usuario.email,
            usuario_nombre=usuario.nombre_completo,
            accion=accion,
            detalle=detalle
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"Error en auditoria: {e}")

# EVENTO STARTUP: Se ejecuta automáticamente cada vez que la API arranca en Render
@app.on_event("startup")
def startup_event():
    migrar_datos_desde_sqlite_si_aplica()
    try:
        db = next(get_db())
        poblar_usuarios_maestros(db)
    except Exception as e:
        print(f"⚠️ Error cargando usuarios maestros en startup: {e}")

# ==============================================================================
# ENDPOINTS REST API
# ==============================================================================

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "version": "9.0.0", "service": "Pruebas Tango ERP Backend"}

# ENDPOINT DE EMERGENCIA PARA FORZAR LA SINCRONIZACIÓN DE TODOS LOS USUARIOS
@app.get("/admin/seed-users", tags=["Administración"])
def seed_users_endpoint(db: Session = Depends(get_db)):
    poblar_usuarios_maestros(db)
    return {
        "status": "ok", 
        "mensaje": "Todos los usuarios administradores y colaboradores fueron sincronizados correctamente con sus contraseñas requeridas.",
        "total_usuarios": len(USUARIOS_PREDEFINIDOS)
    }

# LOGIN
@app.post("/token", response_model=LoginResponse, tags=["Autenticación"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email_clean = form_data.username.strip().lower()
    user = db.query(DBUser).filter(DBUser.email == email_clean).first()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
    
    if not user.activo:
        raise HTTPException(status_code=403, detail="Usuario desactivado. Contacte a Sistemas.")

    registrar_auditoria(db, user, "LOGIN", "Inicio de sesión exitoso")

    access_token = create_access_token(data={"sub": user.email, "rol": user.rol})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "rol": user.rol,
        "nombre_completo": user.nombre_completo,
        "email": user.email
    }

# CREAR USUARIOS MANUALMENTE DESDE EL FRONTEND
@app.post("/admin/usuarios", response_model=UserResponse, tags=["Administración"])
def crear_usuario(usuario: UserCreate, db: Session = Depends(get_db), admin: DBUser = Depends(require_admin)):
    email_clean = usuario.email.strip().lower()
    if db.query(DBUser).filter(DBUser.email == email_clean).first():
        raise HTTPException(status_code=400, detail="El correo electrónico ya existe")
    
    nuevo_usuario = DBUser(
        email=email_clean,
        password_hash=hash_password(usuario.password),
        nombre_completo=usuario.nombre_completo.strip(),
        rol=usuario.rol,
        activo=True
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    registrar_auditoria(db, admin, "CREAR_USUARIO", f"Creó al usuario {nuevo_usuario.nombre_completo} ({nuevo_usuario.email})")
    return nuevo_usuario

@app.get("/admin/usuarios/todos", tags=["Administración"])
def listar_todos_usuarios(db: Session = Depends(get_db), admin: DBUser = Depends(require_admin)):
    users = db.query(DBUser).order_by(DBUser.id.desc()).all()
    return [{
        "id": u.id,
        "email": u.email,
        "nombre_completo": u.nombre_completo,
        "rol": u.rol,
        "activo": u.activo
    } for u in users]

@app.post("/admin/usuarios/{user_id}/reset-password", tags=["Administración"])
def reset_password(user_id: int, payload: dict, db: Session = Depends(get_db), admin: DBUser = Depends(require_admin)):
    nueva_clave = payload.get("nueva_password")
    if not nueva_clave or len(nueva_clave) < 4:
        raise HTTPException(status_code=400, detail="Mínimo 4 caracteres requeridos")
    
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.password_hash = hash_password(nueva_clave)
    db.commit()
    db.refresh(user)

    registrar_auditoria(db, admin, "RESET_PASSWORD", f"Blanqueó contraseña de {user.email}")
    return {"mensaje": f"Contraseña actualizada para {user.email}"}

@app.delete("/admin/usuarios/{user_id}", tags=["Administración"])
def eliminar_usuario(user_id: int, db: Session = Depends(get_db), admin: DBUser = Depends(require_admin)):
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if user.email == admin.email:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")

    email_borrado = user.email
    db.delete(user)
    db.commit()

    registrar_auditoria(db, admin, "ELIMINAR_USUARIO", f"Eliminó al usuario {email_borrado}")
    return {"mensaje": f"Usuario {email_borrado} eliminado correctamente"}

@app.get("/admin/auditoria", tags=["Administración"])
def obtener_auditoria(db: Session = Depends(get_db), admin: DBUser = Depends(require_admin)):
    logs = db.query(DBAuditLog).order_by(DBAuditLog.id.desc()).limit(200).all()
    return [{
        "id": l.id,
        "usuario": f"{l.usuario_nombre} ({l.usuario_email})",
        "accion": l.accion,
        "detalle": l.detalle,
        "fecha": l.fecha.strftime("%Y-%m-%d %H:%M:%S")
    } for l in logs]

@app.get("/modulos", tags=["Catálogos"])
def listar_modulos(db: Session = Depends(get_db), user: DBUser = Depends(get_current_user)):
    return db.query(DBModulo).order_by(DBModulo.nombre.asc()).all()

@app.post("/admin/modulos", tags=["Administración"])
def crear_modulo(mod: ModuloCreate, db: Session = Depends(get_db), admin: DBUser = Depends(require_admin)):
    nombre_limpio = mod.nombre.strip()
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

    existente = db.query(DBModulo).filter(DBModulo.nombre.ilike(nombre_limpio)).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"El módulo '{nombre_limpio}' ya existe")
    
    nuevo = DBModulo(nombre=nombre_limpio)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)

    registrar_auditoria(db, admin, "CREAR_MODULO", f"Creó el módulo '{nuevo.nombre}'")
    return {"mensaje": f"Módulo '{nuevo.nombre}' creado exitosamente", "id": nuevo.id, "nombre": nuevo.nombre}

@app.get("/usuarios/colaboradores", response_model=List[UserResponse], tags=["Usuarios"])
def listar_colaboradores(db: Session = Depends(get_db), user: DBUser = Depends(get_current_user)):
    return db.query(DBUser).filter(DBUser.activo == True).all()

@app.post("/pruebas/registrar-form", tags=["Pruebas"])
async def registrar_prueba_form(
    background_tasks: BackgroundTasks,
    modulo_id: int = Form(...),
    sector_nombre: str = Form(...),
    proceso_nombre: str = Form(...),
    empleado_asignado_id: int = Form(...),
    fase: str = Form(...),
    resultado_estado: str = Form(...),
    fecha_inicio: Optional[str] = Form(None),
    fecha_fin: Optional[str] = Form(None),
    observacion_error: Optional[str] = Form(None),
    enviado_a: Optional[str] = Form(None),
    devolucion_tango: Optional[str] = Form(None),
    archivo_evidencia: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: DBUser = Depends(get_current_user)
):
    asig_id = empleado_asignado_id if user.rol == "ADMIN" else user.id

    proceso_obj = db.query(DBProceso).filter(
        DBProceso.modulo_id == modulo_id,
        DBProceso.nombre == proceso_nombre.strip()
    ).first()

    if not proceso_obj:
        proceso_obj = DBProceso(modulo_id=modulo_id, nombre=proceso_nombre.strip(), descripcion_ruta=proceso_nombre.strip())
        db.add(proceso_obj)
        db.commit()
        db.refresh(proceso_obj)

    ejecucion = db.query(DBEjecucionPrueba).filter(
        DBEjecucionPrueba.proceso_id == proceso_obj.id,
        DBEjecucionPrueba.sector_nombre == sector_nombre
    ).first()

    f_inicio = datetime.datetime.strptime(fecha_inicio, "%Y-%m-%d") if (fecha_inicio and fecha_inicio.strip()) else datetime.datetime.utcnow()
    f_fin = datetime.datetime.strptime(fecha_fin, "%Y-%m-%d") if (fecha_fin and fecha_fin.strip()) else (datetime.datetime.utcnow() if resultado_estado == "Aprobado" else None)

    if not ejecucion:
        ejecucion = DBEjecucionPrueba(
            proceso_id=proceso_obj.id,
            sector_nombre=sector_nombre,
            empleado_asignado_id=asig_id,
            fase=fase,
            estado_actual="Finalizado" if resultado_estado == "Aprobado" else "En curso",
            fecha_inicio=f_inicio,
            fecha_fin=f_fin,
            numero_intento_actual=1
        )
        db.add(ejecucion)
        db.commit()
        db.refresh(ejecucion)
    else:
        ejecucion.numero_intento_actual += 1
        ejecucion.empleado_asignado_id = asig_id
        ejecucion.estado_actual = "Finalizado" if resultado_estado == "Aprobado" else "En curso"
        if f_inicio: ejecucion.fecha_inicio = f_inicio
        if f_fin: ejecucion.fecha_fin = f_fin
        db.commit()
        db.refresh(ejecucion)

    historial = DBHistorialDetalle(
        ejecucion_prueba_id=ejecucion.id,
        numero_intento=ejecucion.numero_intento_actual,
        probado_por_id=user.id,
        observacion_error=observacion_error,
        enviado_a=enviado_a,
        fecha_envio=datetime.datetime.utcnow(),
        devolucion_tango=devolucion_tango,
        resultado_estado=resultado_estado
    )
    db.add(historial)
    db.commit()
    db.refresh(historial)

    if archivo_evidencia and archivo_evidencia.filename:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_clean = f"{timestamp}_{archivo_evidencia.filename.replace(' ', '_')}"
        file_path = os.path.join(UPLOAD_DIR, filename_clean)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(archivo_evidencia.file, buffer)

        adjunto = DBAdjunto(
            historial_id=historial.id,
            nombre_archivo=archivo_evidencia.filename,
            ruta_archivo=f"/uploads/{filename_clean}"
        )
        db.add(adjunto)
        db.commit()

    registrar_auditoria(db, user, "REGISTRO_PRUEBA", f"Registró/Asignó la tarea '{proceso_nombre}'")
    return {"mensaje": f"Prueba registrada con éxito (Intento #{ejecucion.numero_intento_actual})"}

@app.get("/dashboard/gantt", tags=["Dashboard"])
def obtener_monitoreo(
    sector: Optional[str] = None,
    estado: Optional[str] = None,
    asignado_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: DBUser = Depends(get_current_user)
):
    query = db.query(DBEjecucionPrueba)

    if user.rol != "ADMIN":
        query = query.filter(DBEjecucionPrueba.empleado_asignado_id == user.id)
    elif asignado_id:
        query = query.filter(DBEjecucionPrueba.empleado_asignado_id == asignado_id)

    if sector and sector != "TODOS":
        query = query.filter(DBEjecucionPrueba.sector_nombre == sector)
    if estado and estado != "TODOS":
        query = query.filter(DBEjecucionPrueba.estado_actual == estado)

    ejecuciones = query.order_by(DBEjecucionPrueba.id.desc()).all()
    resultado = []

    for ej in ejecuciones:
        proceso = db.query(DBProceso).filter(DBProceso.id == ej.proceso_id).first()
        asignado = db.query(DBUser).filter(DBUser.id == ej.empleado_asignado_id).first()

        primer_hist = db.query(DBHistorialDetalle).filter(
            DBHistorialDetalle.ejecucion_prueba_id == ej.id
        ).order_by(DBHistorialDetalle.numero_intento.asc()).first()

        asignador_nom = "Administrador"
        if primer_hist:
            u_asig = db.query(DBUser).filter(DBUser.id == primer_hist.probado_por_id).first()
            if u_asig: asignador_nom = u_asig.nombre_completo

        f_inicio_str = ej.fecha_inicio.strftime("%Y-%m-%d") if (ej.fecha_inicio and ej.fecha_inicio.year > 2000) else datetime.datetime.utcnow().strftime("%Y-%m-%d")
        f_fin_str = ej.fecha_fin.strftime("%Y-%m-%d") if (ej.fecha_fin and ej.fecha_fin.year > 2000) else "En proceso"

        resultado.append({
            "id": ej.id,
            "proceso_id": ej.proceso_id,
            "proceso": proceso.nombre if proceso else f"Proceso #{ej.proceso_id}",
            "sector": ej.sector_nombre,
            "fase": ej.fase,
            "estado": ej.estado_actual,
            "intento_actual": ej.numero_intento_actual,
            "asignado_a": asignado.nombre_completo if asignado else "Sin asignar",
            "asignado_por": asignador_nom,
            "asignado_id": ej.empleado_asignado_id,
            "fecha_inicio": f_inicio_str,
            "fecha_fin": f_fin_str
        })
    return resultado