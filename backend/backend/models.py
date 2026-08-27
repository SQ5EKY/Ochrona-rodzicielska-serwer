from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, DateTime
from sqlalchemy.orm import relationship
import datetime

from .database import Base

class Parent(Base):
    __tablename__ = "parents"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    
    devices = relationship("Device", back_populates="parent")
    rule = relationship("Rule", back_populates="parent", uselist=False)
    blacklists = relationship("Blacklist", back_populates="parent")
    contacts = relationship("TrustedContact", back_populates="parent")
    sessions = relationship("ParentSession", back_populates="parent")

class ParentSession(Base):
    __tablename__ = "parent_sessions"
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    parent_id = Column(Integer, ForeignKey("parents.id"))
    
    parent = relationship("Parent", back_populates="sessions")

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True)
    name = Column(String)
    os_type = Column(String)
    is_active = Column(Boolean, default=True)
    used_time_seconds = Column(Integer, default=0)
    
    parent_id = Column(Integer, ForeignKey("parents.id"))
    parent = relationship("Parent", back_populates="devices")
    locations = relationship("Location", back_populates="device")

class Rule(Base):
    __tablename__ = "rules"
    id = Column(Integer, primary_key=True, index=True)
    global_time_limit_minutes = Column(Integer, default=120)
    school_time_start = Column(String, default="08:00")
    school_time_end = Column(String, default="14:00")
    is_school_time_active = Column(Boolean, default=True)
    
    parent_id = Column(Integer, ForeignKey("parents.id"))
    parent = relationship("Parent", back_populates="rule")

class Blacklist(Base):
    __tablename__ = "blacklist"
    id = Column(Integer, primary_key=True, index=True)
    item_type = Column(String)
    value = Column(String)
    
    parent_id = Column(Integer, ForeignKey("parents.id"))
    parent = relationship("Parent", back_populates="blacklists")

class TrustedContact(Base):
    __tablename__ = "trusted_contacts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    phone_number = Column(String)
    
    parent_id = Column(Integer, ForeignKey("parents.id"))
    parent = relationship("Parent", back_populates="contacts")

class Location(Base):
    __tablename__ = "locations"
    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    device_id = Column(Integer, ForeignKey("devices.id"))
    device = relationship("Device", back_populates="locations")
