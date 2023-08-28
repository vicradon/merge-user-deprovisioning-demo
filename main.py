from fastapi import FastAPI, Depends, HTTPException
from typing import Dict, Any
from merge.client import Merge
from fastapi_utils.tasks import repeat_every
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import settings

client = Merge(api_key=settings.API_KEY, account_token=settings.BAMBOO_HR_ACCOUNT_TOKEN)

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# fetch updated data
async def fetch_updated_data(last_sync_timestamp, cursor=None, page_size=None):
    modified_employees = client.hris.employees.list(modified_after=last_sync_timestamp,cursor=cursor, page_size=page_size)
    return modified_employees

# sync every 24 hours
@app.on_event("startup")
@repeat_every(seconds=60 * 60 * 24)
async def sync():
    fetch_updated_data()

# respond to webhook requests
@app.post('/employee-modifications')
async def root(json_data: Dict[str, Any]):
    return json_data

@app.get('/employee-modifications')
async def get_employee_modifications(last_sync_timestamp, cursor, page_size):
    updated_data = await fetch_updated_data(last_sync_timestamp, cursor, page_size)
    return updated_data

