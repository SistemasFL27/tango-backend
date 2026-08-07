import os
from app.database import SessionLocal, engine, Base
from app.models import DBUser
from app.auth import hash_password

# Crear tablas si no existen
Base.metadata.create_all(bind=engine)

def rearmar_administrador():
    db = SessionLocal()
    email_admin = "Sistemas@flechalog.com"
    pass_admin = "Admin2626!@"

    # Buscar usuario existente
    user = db.query(DBUser).filter(DBUser.email == email_admin).first()

    if user:
        user.password_hash = hash_password(pass_admin)
        user.rol = "ADMIN"
        user.activo = True
        print(f"✅ Contraseña actualizada con éxito para '{email_admin}'.")
    else:
        nuevo_user = DBUser(
            email=email_admin,
            password_hash=hash_password(pass_admin),
            nombre_completo="Sistemas Flecha Log",
            rol="ADMIN",
            activo=True
        )
        db.add(nuevo_user)
        print(f"✅ Usuario Administrador '{email_admin}' creado desde cero con éxito.")

    db.commit()
    db.close()

if __name__ == "__main__":
    rearmar_administrador()
    