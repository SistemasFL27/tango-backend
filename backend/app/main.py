import os
import shutil
import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app.models import DBUser, DBModulo, DBProceso, DBEjecucionPrueba, DBHistorialDetalle, DBAdjunto
from app.schemas import UserCreate, UserResponse, LoginResponse, ModuloCreate
from app.auth import hash_password, verify_password, create_access_token, get_current_user, require_admin

# Crear tablas
Base.metadata.create_all(bind=engine)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(
    title="Sistema de Pruebas Tango ERP", 
    version="5.3.0"
)

# ==============================================================================
# 1. CONFIGURACIÓN DE CORS
# ==============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inyectar cabeceras CORS incluso en errores 404 u otros fallos de ruta
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=404,
        content={"detail": "Ruta no encontrada en el servidor backend"},
        headers={"Access-Control-Allow-Origin": "*"}
    )

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.get("/", tags=["Infraestructura"])
def root():
    return {"mensaje": "API REST Tango ERP Activa", "status": "online"}

@app.get("/health", tags=["Infraestructura"])
def health_check():
    return {"status": "ok"}

# ==============================================================================
# 2. AUTENTICACIÓN (ENDPOINT POST /token)
# ==============================================================================
@app.post("/token", response_model=LoginResponse, tags=["Autenticación"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(DBUser).filter(DBUser.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Credenciales incorrectas")
    
    access_token = create_access_token(data={"sub": user.email, "rol": user.rol})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "rol": user.rol,
        "nombre_completo": user.nombre_completo,
        "email": user.email
    }

@app.post("/admin/usuarios", response_model=UserResponse, tags=["Administración"])
def crear_usuario(usuario: UserCreate, db: Session = Depends(get_db), admin: DBUser = Depends(require_admin)):
    if db.query(DBUser).filter(DBUser.email == usuario.email).first():
        raise HTTPException(status_code=400, detail="El correo electrónico ya existe")
    
    nuevo_usuario = DBUser(
        email=usuario.email,
        password_hash=hash_password(usuario.password),
        nombre_completo=usuario.nombre_completo,
        rol=usuario.rol,
        activo=True
    )
    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)
    return nuevo_usuario

@app.get("/usuarios/colaboradores", response_model=List[UserResponse], tags=["Usuarios"])
def listar_colaboradores(db: Session = Depends(get_db), user: DBUser = Depends(get_current_user)):
    return db.query(DBUser).filter(DBUser.activo == True).all()

@app.get("/modulos", tags=["Catálogos"])
def listar_modulos(db: Session = Depends(get_db), user: DBUser = Depends(get_current_user)):
    return db.query(DBModulo).order_by(DBModulo.nombre.asc()).all()

@app.post("/admin/modulos", tags=["Administración"])
def crear_modulo(mod: ModuloCreate, db: Session = Depends(get_db), admin: DBUser = Depends(require_admin)):
    nombre_limpio = mod.nombre.strip()
    if not nombre_limpio:
        raise HTTPException(status_code=400, detail="El nombre del módulo no puede estar vacío")

    existente = db.query(DBModulo).filter(DBModulo.nombre.ilike(nombre_limpio)).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"El módulo '{nombre_limpio}' ya existe")
    
    nuevo = DBModulo(nombre=nombre_limpio)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {"mensaje": f"Módulo '{nuevo.nombre}' creado exitosamente", "id": nuevo.id, "nombre": nuevo.nombre}

@app.get("/tareas/mis-pendientes", tags=["Notificaciones"])
def obtener_mis_tareas_pendientes(db: Session = Depends(get_db), user: DBUser = Depends(get_current_user)):
    tareas = db.query(DBEjecucionPrueba).filter(
        DBEjecucionPrueba.empleado_asignado_id == user.id,
        DBEjecucionPrueba.estado_actual == "En curso"
    ).all()

    resultado = []
    for t in tareas:
        proceso = db.query(DBProceso).filter(DBProceso.id == t.proceso_id).first()
        ultimo_hist = db.query(DBHistorialDetalle).filter(
            DBHistorialDetalle.ejecucion_prueba_id == t.id
        ).order_by(DBHistorialDetalle.numero_intento.desc()).first()

        asignador_nom = "Administrador"
        if ultimo_hist:
            u_asig = db.query(DBUser).filter(DBUser.id == ultimo_hist.probado_por_id).first()
            if u_asig: asignador_nom = u_asig.nombre_completo

        resultado.append({
            "ejecucion_id": t.id,
            "proceso_nombre": proceso.nombre if proceso else f"Proceso #{t.proceso_id}",
            "sector": t.sector_nombre,
            "fase": t.fase,
            "intento_actual": t.numero_intento_actual,
            "asignado_por": asignador_nom,
            "fecha_inicio": t.fecha_inicio.strftime("%Y-%m-%d") if t.fecha_inicio else "Sin fecha"
        })
    return resultado

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
        DBProceso.nombre == proceso_nombre
    ).first()

    if not proceso_obj:
        proceso_obj = DBProceso(modulo_id=modulo_id, nombre=proceso_nombre, descripcion_ruta=proceso_nombre)
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

    return {"mensaje": f"Prueba registrada con éxito (Intento #{ejecucion.numero_intento_actual})"}

@app.post("/pruebas/{ejecucion_id}/tomar-completar", tags=["Pruebas"])
async def tomar_y_completar_prueba(
    ejecucion_id: int, 
    resultado_estado: str = Form(...),
    fecha_fin: Optional[str] = Form(None),
    observacion_error: Optional[str] = Form(None),
    devolucion_tango: Optional[str] = Form(None),
    archivo_evidencia: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db), 
    user: DBUser = Depends(get_current_user)
):
    ejecucion = db.query(DBEjecucionPrueba).filter(DBEjecucionPrueba.id == ejecucion_id).first()
    if not ejecucion:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    if user.rol != "ADMIN" and ejecucion.empleado_asignado_id != user.id:
        raise HTTPException(status_code=403, detail="No tienes permiso para completar esta tarea")

    nuevo_estado = "Finalizado" if resultado_estado == "Aprobado" else "En curso"
    ejecucion.estado_actual = nuevo_estado
    
    fecha_fin_real = datetime.datetime.strptime(fecha_fin, "%Y-%m-%d") if (fecha_fin and fecha_fin.strip()) else datetime.datetime.utcnow()
    if resultado_estado == "Aprobado":
        ejecucion.fecha_fin = fecha_fin_real

    historial = DBHistorialDetalle(
        ejecucion_prueba_id=ejecucion.id,
        numero_intento=ejecucion.numero_intento_actual,
        probado_por_id=user.id,
        observacion_error=observacion_error,
        enviado_a="Soporte Tango" if devolucion_tango else None,
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

    return {"mensaje": f"Tarea #{ejecucion_id} actualizada correctamente a estado '{nuevo_estado}'"}

@app.get("/pruebas/{ejecucion_id}/historial", tags=["Pruebas"])
def obtener_historial_prueba(ejecucion_id: int, db: Session = Depends(get_db), user: DBUser = Depends(get_current_user)):
    historial = db.query(DBHistorialDetalle).filter(
        DBHistorialDetalle.ejecucion_prueba_id == ejecucion_id
    ).order_by(DBHistorialDetalle.numero_intento.asc()).all()
    
    resultado = []
    for h in historial:
        usuario = db.query(DBUser).filter(DBUser.id == h.probado_por_id).first()
        adjuntos_list = db.query(DBAdjunto).filter(DBAdjunto.historial_id == h.id).all()
        
        resultado.append({
            "id": h.id,
            "numero_intento": h.numero_intento,
            "probado_por": usuario.nombre_completo if usuario else "Desconocido",
            "observacion_error": h.observacion_error,
            "enviado_a": h.enviado_a,
            "fecha_envio": h.fecha_envio,
            "devolucion_tango": h.devolucion_tango,
            "resultado_estado": h.resultado_estado,
            "fecha_registro": h.fecha_registro,
            "adjuntos": [{"nombre": a.nombre_archivo, "url": a.ruta_archivo} for a in adjuntos_list]
        })
    return resultado

@app.get("/dashboard/gantt", tags=["Dashboard"])
def obtener_gantt(
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

    ejecuciones = query.all()
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