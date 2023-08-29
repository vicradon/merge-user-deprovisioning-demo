from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi_utils.tasks import repeat_every
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from merge.client import Merge
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
import uvicorn
from database import models, schemas
from database.database import SessionLocal, engine
from database.crud import get_user_by_email
import settings

client = Merge(api_key=settings.API_KEY, account_token=settings.BAMBOO_HR_ACCOUNT_TOKEN)

app = FastAPI()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Dependency
def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

# fetch updated data
async def fetch_updated_data(last_sync_timestamp, cursor=None, page_size=None):
    modified_employees = client.hris.employees.list(modified_after=last_sync_timestamp,cursor=cursor, page_size=page_size)
    return modified_employees

async def deprovision_users(users):
    db = SessionLocal()
    for user in users:
        if user.employment_status == "INACTIVE" and user.termination_date is not None and user.termination_date <= datetime.now().isoformat():
            user_in_db = get_user_by_email(db, user.work_email)
            
            if user_in_db is not None:
                user_in_db.is_active = False

    db.commit()
    db.close()

# sync every 24 hours
@app.on_event("startup")
@repeat_every(seconds=60 * 60 * 24)
def sync():
    now = datetime.datetime.now()
    twentyfour_hours_ago = now - datetime.timedelta(hours=24)
    updated_data = fetch_updated_data(last_sync_timestamp=twentyfour_hours_ago.isoformat())
    deprovision_users(updated_data.results)

# respond to webhook requests
@app.post('/employee-modifications')
async def respond_to_employee_modification_webo(webhook_object: Dict[str, Any]):
    deprovision_users([webhook_object.data])

@app.get('/employee-modifications')
async def get_employee_modifications(last_sync_timestamp, cursor=None, page_size=None):
    updated_data = await fetch_updated_data(last_sync_timestamp, cursor, page_size)
    deprovision_users(updated_data.results)
    return updated_data

@app.get("/tasks/", response_model=List[schemas.Task])
def show_records(db: Session = Depends(get_db)):
    tasks = db.query(models.Task).all()
    return tasks

@app.post("/tasks/", response_model=schemas.Task)
def show_records(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    db_item = models.Task(title=task.title, description=task.description)
    db.add(db_item)
    db.commit()

    return db_item

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta or None = None):
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=30)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credential_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("username")

        if username is None:
            raise credential_exception
        
    except JWTError:
        return credential_exception
    
    user = get_user_by_email(db=db, email=username)

    if user is None:
        raise credential_exception
    
    return user

@app.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form_data.username
    password = form_data.password

    user = get_user_by_email(db, email)

    
    if user and user.is_active and verify_password(password, user.hashed_password):
        access_token = create_access_token(data={"username": user.email}, expires_delta=timedelta(minutes=30))
        return {"access_token": access_token, "token_type": "bearer"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

@app.get('/protected')
async def protected(current_user: schemas.User = Depends(get_current_user)):
    return {'hi': current_user}


# Create the users in the app (won't be done in production)
@app.on_event("startup")
def add_users_from_merge():
    models.Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    num_users = db.query(models.User).count()

    if num_users == 0:
        employees = client.hris.employees.list(page_size=100)

        for employee in employees.results:
            if employee.work_email:
                shared_password = "password"
                hashed_password = hash_password(shared_password)
                db_item = models.User(email=employee.work_email, hashed_password=hashed_password, is_active=employee.employment_status=='ACTIVE')
                db.add(db_item)
        
        db.commit()

if __name__ == '__main__':
    uvicorn.run("main:app", port=8000, log_level="info", reload=True)

