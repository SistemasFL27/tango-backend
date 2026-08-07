from app.database import SessionLocal
from app.models import DBUser
from app.auth import hash_password

db = SessionLocal()

admin = db.query(DBUser).filter(DBUser.email == "admin@empresa.com").first()

if admin:
    admin.password_hash = hash_password("Admin1234!")
    admin.rol = "ADMIN"
    admin.activo = True
    print("Contraseña de 'admin@empresa.com' actualizada con éxito a: Admin1234!")
else:
    nuevo_admin = DBUser(
        email="admin@empresa.com",
        password_hash=hash_password("Admin1234!"),
        nombre_completo="Administrador General",
        rol="ADMIN",
        activo=True
    )
    db.add(nuevo_admin)
    print("Usuario 'admin@empresa.com' creado con éxito.")

db.commit()
db.close()