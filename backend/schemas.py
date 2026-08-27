from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class DeviceBase(BaseModel):
    device_id: str
    name: str
    os_type: str

class DeviceCreate(DeviceBase):
    pass

class Device(DeviceBase):
    id: int
    is_active: bool
    used_time_seconds: int
    
    class Config:
        from_attributes = True

class Heartbeat(BaseModel):
    device_id: str
    elapsed_seconds: int

class LocationCreate(BaseModel):
    device_id: str
    latitude: float
    longitude: float

class RuleUpdate(BaseModel):
    global_time_limit_minutes: int
    school_time_start: str
    school_time_end: str
    is_school_time_active: bool

class BlacklistCreate(BaseModel):
    item_type: str
    value: str
