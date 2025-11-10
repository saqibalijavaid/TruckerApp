"""
Configuration Module for Trucker Profit System

This module handles all configuration settings for the Flask application.
It loads configuration from environment variables with sensible defaults.

Configuration Hierarchy:
1. Environment variables (highest priority)
2. Default values (fallback)

Usage:
    from config import MONGO_URI, SECRET_KEY
    
Author: Innocent-X
Last Modified: 2025-11-07
"""

# ============================================================================
# IMPORTS
# ============================================================================
import os
from werkzeug.security import generate_password_hash

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================
# MongoDB connection URI
# Format: mongodb://username:password@host:port/database
# Default: Local MongoDB on port 27017
MONGO_URI = os.environ.get(
    "MONGO_URI", 
    "mongodb://localhost:27017/trucker_profit"
)

# ============================================================================
# FLASK CONFIGURATION
# ============================================================================
# Secret key for encrypting session data and CSRF tokens
# ⚠️  IMPORTANT: Change this to a random string in production
SECRET_KEY = os.environ.get(
    "SECRET_KEY", 
    "qwerty12345678"  # Default: NOT SECURE - change immediately
)

# Application environment
FLASK_ENV = os.environ.get("FLASK_ENV", "development")

# Debug mode (disabled in production)
FLASK_DEBUG = FLASK_ENV == "development"

# ============================================================================
# SESSION CONFIGURATION
# ============================================================================
# Security settings for session cookies
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to cookies
SESSION_COOKIE_SECURE = os.environ.get("SESSION_SECURE", "False").lower() == "true"
SESSION_COOKIE_SAMESITE = "Lax"  # CSRF protection

# ============================================================================
# AUTHENTICATION CONFIGURATION
# ============================================================================
# Admin/Owner credentials
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")

# Default admin password hash (for "admin123")
# In production, use environment variable or secure credential manager
ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH",
    generate_password_hash(os.environ.get("ADMIN_PASSWORD", "admin123"))
)

# ============================================================================
# EXCHANGE RATE API CONFIGURATION
# ============================================================================
# Supported providers: exchangerate-api, fixer, openexchangerates
EXCHANGE_RATE_API_PROVIDER = os.environ.get(
    "EXCHANGE_RATE_API_PROVIDER", 
    "exchangerate-api"
)

# API key for exchange rate provider (optional for exchangerate-api free tier)
EXCHANGE_RATE_API_KEY = os.environ.get(
    "EXCHANGE_RATE_API_KEY", 
    "your_api_key_here"
)

# Default exchange rate (USD to CAD) as fallback
# Used if API is unavailable
DEFAULT_EXCHANGE_RATE = float(
    os.environ.get("DEFAULT_EXCHANGE_RATE", 1.35)
)

# ============================================================================
# FILE UPLOAD CONFIGURATION
# ============================================================================
# Directory for storing uploaded files (receipts, photos, etc.)
UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed file extensions for upload
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}

# Maximum file size in MB
MAX_FILE_SIZE_MB = 10

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
# Log level
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Log file path
LOG_FILE = os.environ.get("LOG_FILE", "logs/app.log")

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# ============================================================================
# APPLICATION FEATURES
# ============================================================================
# Trip management settings
TRIP_COMPLETION_EXPENSE_WINDOW_HOURS = 24  # Hours to add expenses after completion

# ============================================================================
# SECURITY HEADERS
# ============================================================================
# CORS origins (comma-separated)
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5000")

# ============================================================================
# SUMMARY
# ============================================================================
"""
Configuration Summary:
- Database: MongoDB (MONGO_URI)
- Authentication: Owner/Driver roles with hashed passwords
- Exchange Rates: Live API with caching (1-hour)
- File Uploads: Images and PDFs (max 10MB)
- Security: HTTPS in production, secure cookies, CSRF protection
- Logging: Application events logged to file and console

To override defaults, set environment variables in .env file
and load with: python-dotenv or similar tool
"""