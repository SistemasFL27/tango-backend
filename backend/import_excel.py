import os
import datetime
import pandas as pd
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine, Base
from app.models import DBUser, DBModulo, DBProceso, DBEjecucionPrueba, DBHistorialDetalle
from app.auth import hash_password

# Crear tablas si aún no existen
Base.metadata.create_all(bind=engine)

def migrar_excel():
    excel_path = "../AVANCE ETAPA PRUEBA - TANGO (1).xlsx"
    if not os.path.exists(excel_path):
        excel_path = "AVANCE ETAPA PRUEBA - TANGO (1).xlsx"
    
    if not os.path.exists(excel_path):
        print(f"Error: No se encontró el archivo Excel en {excel_path}")
        return

    db: Session = SessionLocal()
    xls = pd.ExcelFile(excel_path)
    print("Iniciando migración desde Excel...")

    # 1. Cargar Usuarios desde la hoja de Desplegables
    if 'Teclas desplegables  no elimina' in xls.sheet_names:
        df_drop = pd.read_excel(xls, 'Teclas desplegables  no elimina', header=None)
        # La columna index 8 contiene los responsables
        responsables = df_drop.iloc[2:, 8].dropna().unique()
        for resp in responsables:
            nombre = str(resp).strip()
            email = f"{nombre.lower().replace(' ', '.')}@empresa.com"
            if not db.query(DBUser).filter(DBUser.email == email).first():
                db.add(DBUser(
                    email=email,
                    password_hash=hash_password("Tango2026!"),
                    nombre_completo=nombre,
                    rol="COLABORADOR"
                ))
        db.commit()

    # 2. Procesar Hojas de Módulos
    modulos_sheets = [s for s in xls.sheet_names if s.startswith('MODULO') or s == 'TAREAS PENDIENTES']

    for sheet in modulos_sheets:
        df = pd.read_excel(xls, sheet, header=None)
        
        # Buscar la fila donde están los encabezados (donde col 0 == 'FECHA PRUEBA' o col 1 == 'FECHA')
        header_row = -1
        for idx, row in df.iterrows():
            row_str = " ".join([str(val) for val in row.values if pd.notna(val)])
            if 'FECHA' in row_str and 'FASE' in row_str and 'TAREA' in row_str:
                header_row = idx
                break

        if header_row == -1:
            continue

        # Extraer filas de datos a partir de header_row + 1
        for idx in range(header_row + 1, len(df)):
            row = df.iloc[idx]
            if row.dropna().empty:
                continue

            fecha_val = row.iloc[0] if pd.notna(row.iloc[0]) else row.iloc[1]
            if not isinstance(fecha_val, (datetime.datetime, pd.Timestamp)):
                fecha_prueba = datetime.datetime.now()
            else:
                fecha_prueba = fecha_val

            fase = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else "Prueba"
            modulo_nom = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else sheet.replace("MODULO ", "").capitalize()
            estado = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else "En curso"
            tarea_nom = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else "Proceso General"
            asignado_nom = str(row.iloc[5]).strip() if pd.notna(row.iloc[5]) else "Administrador"
            observacion = str(row.iloc[6]).strip() if pd.notna(row.iloc[6]) else None
            
            # Columnas de devolución Tango
            fecha_envio = row.iloc[8] if len(row) > 8 and pd.notna(row.iloc[8]) else None
            if not isinstance(fecha_envio, (datetime.datetime, pd.Timestamp)):
                fecha_envio = None
            devolucion = str(row.iloc[9]).strip() if len(row) > 9 and pd.notna(row.iloc[9]) else None

            # Garantizar Módulo
            modulo_obj = db.query(DBModulo).filter(DBModulo.nombre == modulo_nom).first()
            if not modulo_obj:
                modulo_obj = DBModulo(nombre=modulo_nom)
                db.add(modulo_obj)
                db.commit()
                db.refresh(modulo_obj)

            # Garantizar Proceso / Tarea
            proceso_obj = db.query(DBProceso).filter(
                DBProceso.modulo_id == modulo_obj.id,
                DBProceso.nombre == tarea_nom
            ).first()
            if not proceso_obj:
                proceso_obj = DBProceso(
                    modulo_id=modulo_obj.id,
                    nombre=tarea_nom,
                    descripcion_ruta=tarea_nom
                )
                db.add(proceso_obj)
                db.commit()
                db.refresh(proceso_obj)

            # Garantizar Usuario asignado
            user_email = f"{asignado_nom.lower().replace(' ', '.')}@empresa.com"
            user_obj = db.query(DBUser).filter(DBUser.email == user_email).first()
            if not user_obj:
                user_obj = DBUser(
                    email=user_email,
                    password_hash=hash_password("Tango2026!"),
                    nombre_completo=asignado_nom,
                    rol="COLABORADOR"
                )
                db.add(user_obj)
                db.commit()
                db.refresh(user_obj)

            # Registrar Ejecución de Prueba
            ejecucion = db.query(DBEjecucionPrueba).filter(
                DBEjecucionPrueba.proceso_id == proceso_obj.id,
                DBEjecucionPrueba.sector_nombre == modulo_nom
            ).first()

            if not ejecucion:
                ejecucion = DBEjecucionPrueba(
                    proceso_id=proceso_obj.id,
                    sector_nombre=modulo_nom,
                    empleado_asignado_id=user_obj.id,
                    fase=fase,
                    estado_actual=estado,
                    fecha_inicio=fecha_prueba,
                    numero_intento_actual=1
                )
                db.add(ejecucion)
                db.commit()
                db.refresh(ejecucion)
            else:
                ejecucion.numero_intento_actual += 1
                ejecucion.estado_actual = estado
                db.commit()

            # Registrar Historial
            historial = DBHistorialDetalle(
                ejecucion_prueba_id=ejecucion.id,
                numero_intento=ejecucion.numero_intento_actual,
                probado_por_id=user_obj.id,
                observacion_error=observacion,
                enviado_a="Soporte Tango" if devolucion else None,
                fecha_envio=fecha_envio,
                devolucion_tango=devolucion,
                resultado_estado="Aprobado" if estado == "Finalizado" else "Fallido"
            )
            db.add(historial)
            db.commit()

    db.close()
    print("¡Migración completada con éxito!")

if __name__ == "__main__":
    migrar_excel()
    