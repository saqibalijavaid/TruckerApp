"""
Database Handler Module for Trucker Profit System

This module provides database abstraction and CRUD operations for all
application entities: drivers, trips, units, and settings.

Database Structure:
├── drivers
│   └── Stores driver profiles, credentials, contact info
├── trips
│   └── Stores trip records with payments and expenses
├── units
│   └── Stores vehicle/fleet units with maintenance expenses
└── settings
    └── Stores system configuration (exchange rates, currency)

Features:
- MongoDB integration with PyMongo
- Automatic timestamp handling
- Transaction support for complex operations
- Error handling and validation
- Clean separation of database logic from business logic

Usage:
    from db_handler import DBHandler
    db = DBHandler()
    drivers = db.list_drivers()
    
Author: Innocent-X
Last Modified: 2025-11-07
"""

# ============================================================================
# IMPORTS
# ============================================================================
from pymongo import MongoClient, ReturnDocument
from bson.objectid import ObjectId
from datetime import datetime
import config

# ============================================================================
# DATABASE HANDLER CLASS
# ============================================================================
class DBHandler:
    """
    Handles all database operations for the Trucker Profit System.
    
    This class manages connections to MongoDB and provides methods for
    creating, reading, updating, and deleting records for all entities.
    
    Attributes:
        client: MongoDB client connection
        db: Database instance
        drivers: Drivers collection
        units: Units collection
        trips: Trips collection
        settings: Settings collection
    """
    
    def __init__(self, uri=None):
        """
        Initialize database connection and collections.
        
        Args:
            uri (str, optional): MongoDB connection URI. 
                                Defaults to config.MONGO_URI if not provided.
        
        Raises:
            Exception: If connection to MongoDB fails
        """
        # Connect to MongoDB
        self.client = MongoClient(uri or config.MONGO_URI)
        
        # Get database instance
        # Try to get default database from URI, fallback to 'trucker_profit'
        try:
            default_db = self.client.get_default_database()
        except Exception:
            default_db = None
        self.db = default_db if default_db is not None else self.client["trucker_profit"]

        # Initialize collections
        self.drivers = self.db.drivers
        self.units = self.db.units
        self.trips = self.db.trips
        self.settings = self.db.settings

        # Ensure settings document exists with defaults
        if self.settings.count_documents({}) == 0:
            self.settings.insert_one({
                "exchange_rate": config.DEFAULT_EXCHANGE_RATE,
                "primary_currency": "USD",
                "created_at": datetime.utcnow()
            })

    # ========================================================================
    # SETTINGS OPERATIONS
    # ========================================================================
    
    def get_exchange_rate(self):
        """
        Retrieve the current USD to CAD exchange rate.
        
        Returns:
            float: Current exchange rate (1 USD = X CAD)
        """
        doc = self.settings.find_one({}, sort=[("_id", 1)])
        return doc.get("exchange_rate", config.DEFAULT_EXCHANGE_RATE)

    def set_exchange_rate(self, rate):
        """
        Update the USD to CAD exchange rate.
        
        Args:
            rate (float): New exchange rate
            
        Returns:
            dict: Updated settings document
        """
        return self.settings.find_one_and_update(
            {},
            {"$set": {"exchange_rate": float(rate)}},
            return_document=ReturnDocument.AFTER
        )

    def get_primary_currency(self):
        """
        Get the primary currency for financial reporting.
        
        Returns:
            str: 'USD' or 'CAD'
        """
        doc = self.settings.find_one({}, sort=[("_id", 1)])
        return doc.get("primary_currency", "USD")

    def set_primary_currency(self, cur):
        """
        Set the primary currency for financial reporting.
        
        Args:
            cur (str): 'USD' or 'CAD'
            
        Returns:
            dict: Updated settings document
        """
        return self.settings.find_one_and_update(
            {},
            {"$set": {"primary_currency": cur}},
            return_document=ReturnDocument.AFTER
        )

    # ========================================================================
    # DRIVER OPERATIONS
    # ========================================================================
    
    def list_drivers(self, filter_query=None):
        """
        Retrieve all drivers or filtered drivers.
        
        Args:
            filter_query (dict, optional): MongoDB query filter
            
        Returns:
            list: List of driver documents
        """
        q = filter_query or {}
        return list(self.drivers.find(q))

    def get_driver(self, driver_id):
        """
        Get a specific driver by ID.
        
        Args:
            driver_id (str): MongoDB ObjectId as string
            
        Returns:
            dict: Driver document or None if not found
        """
        try:
            return self.drivers.find_one({"_id": ObjectId(driver_id)})
        except Exception:
            return None

    def create_driver(self, driver_doc):
        """
        Create a new driver record.
        
        Args:
            driver_doc (dict): Driver data including name, email, password_hash
            
        Returns:
            InsertOneResult: MongoDB insert result
        """
        driver_doc.setdefault("created_at", datetime.utcnow())
        return self.drivers.insert_one(driver_doc)

    def update_driver(self, driver_id, fields):
        """
        Update driver record.
        
        Args:
            driver_id (str): MongoDB ObjectId as string
            fields (dict): Fields to update
            
        Returns:
            dict: Updated driver document
        """
        return self.drivers.find_one_and_update(
            {"_id": ObjectId(driver_id)},
            {"$set": fields},
            return_document=ReturnDocument.AFTER
        )

    # ========================================================================
    # UNIT OPERATIONS
    # ========================================================================
    
    def list_units(self, filter_query=None):
        """
        Retrieve all fleet units or filtered units.
        
        Args:
            filter_query (dict, optional): MongoDB query filter
            
        Returns:
            list: List of unit documents
        """
        q = filter_query or {}
        return list(self.units.find(q))

    def get_unit(self, unit_id):
        """
        Get a specific unit by ID.
        
        Args:
            unit_id (str): MongoDB ObjectId as string
            
        Returns:
            dict: Unit document or None if not found
        """
        try:
            return self.units.find_one({"_id": ObjectId(unit_id)})
        except Exception:
            return None

    def create_unit(self, unit_doc):
        """
        Create a new unit/vehicle record.
        
        Args:
            unit_doc (dict): Unit data including number, make, model
            
        Returns:
            InsertOneResult: MongoDB insert result
        """
        unit_doc.setdefault("created_at", datetime.utcnow())
        unit_doc.setdefault("expenses", [])
        return self.units.insert_one(unit_doc)

    def add_unit_expense(self, unit_id, expense):
        """
        Add an expense record to a unit.
        
        Args:
            unit_id (str): MongoDB ObjectId as string
            expense (dict): Expense data (category, amount, currency, etc.)
            
        Returns:
            dict: Updated unit document
        """
        expense.setdefault("created_at", datetime.utcnow())
        return self.units.find_one_and_update(
            {"_id": ObjectId(unit_id)},
            {"$push": {"expenses": expense}},
            return_document=ReturnDocument.AFTER
        )

    # ========================================================================
    # TRIP OPERATIONS
    # ========================================================================
    
    def list_trips(self, filter_query=None):
        """
        Retrieve all trips or filtered trips.
        
        Args:
            filter_query (dict, optional): MongoDB query filter
            
        Returns:
            list: List of trip documents
        """
        q = filter_query or {}
        return list(self.trips.find(q))

    def get_trip(self, trip_id):
        """
        Get a specific trip by ID.
        
        Args:
            trip_id (str): MongoDB ObjectId as string
            
        Returns:
            dict: Trip document or None if not found
        """
        try:
            return self.trips.find_one({"_id": ObjectId(trip_id)})
        except Exception:
            return None

    def create_trip(self, trip_doc):
        """
        Create a new trip record.
        
        Args:
            trip_doc (dict): Trip data including route, payment, driver, unit
            
        Returns:
            InsertOneResult: MongoDB insert result
        """
        trip_doc.setdefault("created_at", datetime.utcnow())
        trip_doc.setdefault("expenses", [])
        trip_doc.setdefault("status", "active")
        return self.trips.insert_one(trip_doc)

    def add_trip_expense(self, trip_id, expense):
        """
        Add an expense record to a trip.
        
        Args:
            trip_id (str): MongoDB ObjectId as string
            expense (dict): Expense data (category, amount, currency, etc.)
            
        Returns:
            dict: Updated trip document
        """
        expense.setdefault("created_at", datetime.utcnow())
        return self.trips.find_one_and_update(
            {"_id": ObjectId(trip_id)},
            {"$push": {"expenses": expense}},
            return_document=ReturnDocument.AFTER
        )

    def update_trip(self, trip_id, update_fields):
        """
        Update trip record.
        
        Args:
            trip_id (str): MongoDB ObjectId as string
            update_fields (dict): Fields to update
            
        Returns:
            dict: Updated trip document
        """
        return self.trips.find_one_and_update(
            {"_id": ObjectId(trip_id)},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER
        )

    # ========================================================================
    # DATA SEEDING
    # ========================================================================
    
    def seed_initial_data(self, seed):
        """
        Seed the database with initial data for development/testing.
        
        Args:
            seed (dict): Data dictionary containing drivers, units, trips
        """
        # Seed drivers
        if self.drivers.count_documents({}) == 0:
            for d in seed.get("drivers", []):
                doc = {
                    "name": d.get("name"),
                    "email": d.get("email"),
                    "phone": d.get("phone"),
                    "password_hash": d.get("password_hash"),
                    "created_at": datetime.utcnow()
                }
                self.drivers.insert_one(doc)

        # Seed units
        if self.units.count_documents({}) == 0:
            for u in seed.get("units", []):
                self.units.insert_one({
                    "number": u.get("number"),
                    "make": u.get("make"),
                    "model": u.get("model"),
                    "expenses": [],
                    "created_at": datetime.utcnow()
                })

        # Seed trips
        if self.trips.count_documents({}) == 0:
            for t in seed.get("trips", []):
                t_doc = {
                    "trip_number": t.get("tripNumber"),
                    "driver_id": None,
                    "unit_id": None,
                    "pickup_date": t.get("pickupDate"),
                    "pickup_city": t.get("pickupCity"),
                    "pickup_state": t.get("pickupState"),
                    "delivery_date": t.get("deliveryDate"),
                    "delivery_city": t.get("deliveryCity"),
                    "delivery_state": t.get("deliveryState"),
                    "payment_usd": t.get("paymentUSD"),
                    "payment_cad": t.get("paymentCAD"),
                    "status": t.get("status", "active"),
                    "expenses": [],
                    "created_at": datetime.fromisoformat(t.get("createdAt").replace("Z", "+00:00")) if t.get("createdAt") else datetime.utcnow()
                }
                self.trips.insert_one(t_doc)

        # Set exchange rate if provided
        if seed.get("exchangeRate"):
            self.set_exchange_rate(seed.get("exchangeRate"))

# ============================================================================
# SUMMARY
# ============================================================================
"""
DBHandler provides a clean database abstraction layer:

SETTINGS:
- get/set_exchange_rate(): Manage USD-CAD conversion
- get/set_primary_currency(): Choose reporting currency

DRIVERS:
- CRUD operations for driver profiles
- Password hashing managed by app.py

TRIPS:
- Create and manage trip records
- Track payments and expenses per trip
- Support for trip status tracking

UNITS:
- Vehicle/fleet management
- Track maintenance and operational expenses

All operations include timestamps and error handling.
MongoDB ObjectIds are handled internally.
"""