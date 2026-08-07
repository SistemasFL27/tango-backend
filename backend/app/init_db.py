from app.database import SessionLocal, engine, Base
from app.models import DBUser, DBModulo
from app.auth import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# Usuario Administrador Principal
admin_email = "Sistemas@flechalog.com"
admin_user = db.query(DBUser).filter(DBUser.email == admin_email).first()

if not admin_user:
    nuevo_admin = DBUser(
        email=admin_email,
        password_hash=hash_password("Admin2626!@"),
        nombre_completo="Administrador de Sistemas",
        rol="ADMIN",
        activo=True
    )
    db.add(nuevo_admin)
    print(f"Usuario Administrador '{admin_email}' creado exitosamente.")
else:
    admin_user.password_hash = hash_password("Admin2626!@")
    admin_user.rol = "ADMIN"
    print(f"Credenciales de '{admin_email}' actualizadas correctamente.")

db.commit()
db.close()