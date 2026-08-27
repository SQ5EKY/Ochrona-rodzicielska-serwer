import hashlib
import uuid
import random
import string
from datetime import datetime, time

from fastapi import FastAPI, Depends, Request, Form, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import os

from . import models, schemas
from .database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Stealth Parental API (Global)", debug=True)
templates = Jinja2Templates(directory="backend/templates")

import traceback

@app.exception_handler(500)
async def internal_exception_handler(request: Request, exc: Exception):
    return HTMLResponse(content=f"<pre>Error 500:\n{traceback.format_exc()}</pre>", status_code=500)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return HTMLResponse(content=f"<pre>Unhandled Error:\n{traceback.format_exc()}</pre>", status_code=500)

# Obsługa plików statycznych (np. pobieranie aplikacji)
os.makedirs("backend/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="backend/static"), name="static")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_parent(request: Request, db: Session):
    session_token = request.cookies.get("session_id")
    if not session_token:
        return None
    user_session = db.query(models.ParentSession).filter(models.ParentSession.token == session_token).first()
    if not user_session:
        return None
    return db.query(models.Parent).filter(models.Parent.id == user_session.parent_id).first()

# --- API DLA URZĄDZEŃ (DZIECKO) ---

@app.post("/api/heartbeat")
def heartbeat(data: schemas.Heartbeat, db: Session = Depends(get_db)):
    # Urządzenie podaje swój unikalny kod
    device = db.query(models.Device).filter(models.Device.device_id == data.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    device.used_time_seconds += data.elapsed_seconds
    db.commit()
    
    parent_id = device.parent_id
    rules = db.query(models.Rule).filter(models.Rule.parent_id == parent_id).first()
    
    if not rules:
        return {"status": "ok", "lock_device": False, "blacklist": [], "contacts": []}
        
    blacklist = db.query(models.Blacklist).filter(models.Blacklist.parent_id == parent_id).all()
    contacts = db.query(models.TrustedContact).filter(models.TrustedContact.parent_id == parent_id).all()
    
    now = datetime.now().time()
    try:
        start_t = datetime.strptime(rules.school_time_start, "%H:%M").time()
        end_t = datetime.strptime(rules.school_time_end, "%H:%M").time()
        in_school_time = rules.is_school_time_active and (start_t <= now <= end_t)
    except:
        in_school_time = False

    time_exhausted = (device.used_time_seconds / 60) >= rules.global_time_limit_minutes

    return {
        "status": "ok",
        "lock_device": time_exhausted or in_school_time,
        "reason": "school_time" if in_school_time else ("time_exhausted" if time_exhausted else None),
        "blacklist": [{"type": b.item_type, "value": b.value} for b in blacklist],
        "contacts": [{"name": c.name, "phone": c.phone_number} for c in contacts]
    }

@app.post("/api/location")
def update_location(data: schemas.LocationCreate, db: Session = Depends(get_db)):
    device = db.query(models.Device).filter(models.Device.device_id == data.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    loc = models.Location(device_id=device.id, latitude=data.latitude, longitude=data.longitude)
    db.add(loc)
    db.commit()
    return {"status": "ok"}


# --- PANEL RODZICA I STRONA (SaaS Frontend) ---

@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request):
    try:
        return templates.TemplateResponse(request=request, name="landing.html")
    except Exception as e:
        import traceback
        return HTMLResponse(content=f"<pre>Error in landing_page:\n{traceback.format_exc()}</pre>", status_code=500)

@app.get("/download/windows")
def download_windows():
    file_path = "backend/static/StealthParental.exe"
    if os.path.exists(file_path):
        return FileResponse(path=file_path, filename="StealthParental.exe", media_type="application/vnd.microsoft.portable-executable")
    raise HTTPException(status_code=404, detail="Aplikacja dla Windows jest w trakcie aktualizacji. Spróbuj ponownie później.")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    pwd_hash = hash_password(password)
    parent = db.query(models.Parent).filter(models.Parent.email == email, models.Parent.password_hash == pwd_hash).first()
    
    if parent:
        token = str(uuid.uuid4())
        session = models.ParentSession(token=token, parent_id=parent.id)
        db.add(session)
        db.commit()
        
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="session_id", value=token, httponly=True)
        return response
        
    return templates.TemplateResponse(request=request, name="login.html", context={"error": "Błędny email lub hasło!"})

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")

@app.post("/register")
def register(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(models.Parent).filter(models.Parent.email == email).first():
        return templates.TemplateResponse(request=request, name="register.html", context={"error": "Ten email jest już zarejestrowany!"})
        
    new_parent = models.Parent(email=email, password_hash=hash_password(password))
    db.add(new_parent)
    db.commit()
    db.refresh(new_parent)
    
    # Create default rule for new parent
    default_rule = models.Rule(parent_id=new_parent.id)
    db.add(default_rule)
    db.commit()
    
    return templates.TemplateResponse(request=request, name="login.html", context={"success": "Konto założone! Możesz się zalogować."})

@app.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    session_token = request.cookies.get("session_id")
    if session_token:
        db.query(models.ParentSession).filter(models.ParentSession.token == session_token).delete()
        db.commit()
        
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session_id")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    parent = get_current_parent(request, db)
    if not parent: return RedirectResponse(url="/")
        
    rule = db.query(models.Rule).filter(models.Rule.parent_id == parent.id).first()
    devices = db.query(models.Device).filter(models.Device.parent_id == parent.id).all()
    blacklist = db.query(models.Blacklist).filter(models.Blacklist.parent_id == parent.id).all()
    contacts = db.query(models.TrustedContact).filter(models.TrustedContact.parent_id == parent.id).all()
    
    locations = {}
    for d in devices:
        last_loc = db.query(models.Location).filter(models.Location.device_id == d.id).order_by(models.Location.id.desc()).first()
        if last_loc: locations[d.name] = last_loc

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "parent": parent,
        "rule": rule, 
        "devices": devices, 
        "blacklist": blacklist,
        "locations": locations,
        "contacts": contacts
    })

# --- Zarządzanie danymi powiązanymi z kontem ---

@app.post("/dashboard/rules")
def update_rules(
    request: Request, limit: int = Form(...), school_start: str = Form(...), school_end: str = Form(...), school_active: bool = Form(False), db: Session = Depends(get_db)
):
    parent = get_current_parent(request, db)
    if not parent: return RedirectResponse(url="/")
        
    rule = db.query(models.Rule).filter(models.Rule.parent_id == parent.id).first()
    rule.global_time_limit_minutes = limit
    rule.school_time_start = school_start
    rule.school_time_end = school_end
    rule.is_school_time_active = school_active
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/dashboard/devices")
def add_device(request: Request, name: str = Form(...), os_type: str = Form(...), db: Session = Depends(get_db)):
    parent = get_current_parent(request, db)
    if not parent: return RedirectResponse(url="/")
        
    short_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    new_device = models.Device(device_id=short_id, name=name, os_type=os_type, parent_id=parent.id)
    db.add(new_device)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/dashboard/devices/delete/{dev_id}")
def delete_device(dev_id: int, request: Request, db: Session = Depends(get_db)):
    parent = get_current_parent(request, db)
    if not parent: return RedirectResponse(url="/")
    
    device = db.query(models.Device).filter(models.Device.id == dev_id, models.Device.parent_id == parent.id).first()
    if device:
        db.query(models.Location).filter(models.Location.device_id == device.id).delete()
        db.delete(device)
        db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/dashboard/blacklist")
def add_blacklist(request: Request, item_type: str = Form(...), value: str = Form(...), db: Session = Depends(get_db)):
    parent = get_current_parent(request, db)
    if not parent: return RedirectResponse(url="/")
        
    item = models.Blacklist(item_type=item_type, value=value, parent_id=parent.id)
    db.add(item)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/dashboard/blacklist/delete/{item_id}")
def delete_blacklist(item_id: int, request: Request, db: Session = Depends(get_db)):
    parent = get_current_parent(request, db)
    if not parent: return RedirectResponse(url="/")
        
    item = db.query(models.Blacklist).filter(models.Blacklist.id == item_id, models.Blacklist.parent_id == parent.id).first()
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/dashboard/contacts")
def add_contact(request: Request, name: str = Form(...), phone: str = Form(...), db: Session = Depends(get_db)):
    parent = get_current_parent(request, db)
    if not parent: return RedirectResponse(url="/")
        
    new_contact = models.TrustedContact(name=name, phone_number=phone, parent_id=parent.id)
    db.add(new_contact)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@app.post("/dashboard/contacts/delete/{contact_id}")
def delete_contact(contact_id: int, request: Request, db: Session = Depends(get_db)):
    parent = get_current_parent(request, db)
    if not parent: return RedirectResponse(url="/")
        
    contact = db.query(models.TrustedContact).filter(models.TrustedContact.id == contact_id, models.TrustedContact.parent_id == parent.id).first()
    if contact:
        db.delete(contact)
        db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)
