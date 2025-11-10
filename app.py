# -*- coding: utf-8 -*-
"""
Main Flask application file for the Trucker Profit System.
WITH COMPREHENSIVE SECURITY

Author: Innocent-X
Last Modified: 2025-11-07
"""

# Standard library imports
import os
import logging
from datetime import datetime, timedelta
from functools import wraps

# Third-party imports
from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, send_from_directory, make_response)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId

# Local application imports
import config
from db_handler import DBHandler
from exchange_rate_service import ExchangeRateService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# FLASK APP INITIALIZATION
# ============================================================================

app = Flask(__name__)

# Load configuration
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['SESSION_COOKIE_HTTPONLY'] = config.SESSION_COOKIE_HTTPONLY
app.config['SESSION_COOKIE_SECURE'] = config.SESSION_COOKIE_SECURE
app.config['SESSION_COOKIE_SAMESITE'] = config.SESSION_COOKIE_SAMESITE
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Initialize database
db = DBHandler()


# ============================================================================
# SECURITY DECORATORS FOR ROUTE PROTECTION
# ============================================================================
@app.route("/clear-session", methods=["POST"])
def clear_session():
    """
    Clear the session from server.
    Called when user navigates back to login page.
    """
    user_info = session.get('user_name', 'User')
    logger.info(f"🔙 Session cleared for {user_info} at {datetime.utcnow()}")
    session.clear()
    return {"status": "success", "message": "Session cleared"}, 200

@app.route("/check-auth")
def check_auth():
    """
    Check if user is authenticated.
    Used when user navigates via browser forward button.
    Returns 200 if authenticated, 401 if not.
    """
    if 'user_id' not in session or not validate_session():
        return {"status": "not_authenticated"}, 401
    return {"status": "authenticated"}, 200


def require_login(f):
    """Decorator to require user login for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user_id exists in session
        if 'user_id' not in session:
            logger.warning(f"Unauthorized access attempt to {request.endpoint} from {request.remote_addr}")
            flash("❌ You must login first to access this page.", "error")
            return redirect(url_for('login'))
        
        # Additional security: verify session is valid
        if not validate_session():
            logger.warning(f"Invalid session detected for {request.endpoint}")
            session.clear()
            flash("❌ Your session is invalid. Please login again.", "error")
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function


def require_owner(f):
    """Decorator to require owner role for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First check if logged in
        if 'user_id' not in session:
            logger.warning(f"Unauthorized owner access attempt to {request.endpoint} from {request.remote_addr}")
            flash("❌ You must login first.", "error")
            return redirect(url_for('login'))
        
        # Check if user is owner
        if session.get('user_role') != 'owner':
            logger.warning(f"Non-owner access attempt to {request.endpoint} by {session.get('user_id')}")
            flash("❌ Access denied. Owner role required.", "error")
            return redirect(url_for('login'))
        
        # Validate session
        if not validate_session():
            logger.warning(f"Invalid session for owner access to {request.endpoint}")
            session.clear()
            flash("❌ Your session is invalid. Please login again.", "error")
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function


def require_driver(f):
    """Decorator to require driver role for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First check if logged in
        if 'user_id' not in session:
            logger.warning(f"Unauthorized driver access attempt to {request.endpoint} from {request.remote_addr}")
            flash("❌ You must login first.", "error")
            return redirect(url_for('login'))
        
        # Check if user is driver
        if session.get('user_role') != 'driver':
            logger.warning(f"Non-driver access attempt to {request.endpoint} by {session.get('user_id')}")
            flash("❌ Access denied. Driver role required.", "error")
            return redirect(url_for('login'))
        
        # Validate session
        if not validate_session():
            logger.warning(f"Invalid session for driver access to {request.endpoint}")
            session.clear()
            flash("❌ Your session is invalid. Please login again.", "error")
            return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# SESSION VALIDATION
# ============================================================================

def validate_session():
    """
    Validate that the session is legitimate and hasn't been tampered with.
    Returns True if valid, False otherwise.
    """
    required_fields = ['user_id', 'user_role', 'user_name']
    
    # Check if all required fields exist
    for field in required_fields:
        if field not in session:
            return False
    
    # Validate user_role is one of the allowed values
    if session.get('user_role') not in ['owner', 'driver']:
        return False
    
    # If owner, user_id should be 'owner'
    if session.get('user_role') == 'owner' and session.get('user_id') != 'owner':
        return False
    
    # If driver, user_id should be a valid MongoDB ObjectId string
    if session.get('user_role') == 'driver':
        try:
            ObjectId(session.get('user_id'))
        except:
            return False
    
    return True


# ============================================================================
# MIDDLEWARE - SECURITY & VALIDATION
# ============================================================================

@app.before_request
def before_request():
    """
    Security middleware: runs before every request.
    Validates session and enforces authentication on protected routes.
    """
    # Public routes that don't require authentication
    public_routes = ['login', 'logout', 'static', 'uploaded_file']
    
    # If accessing public route, allow it
    if request.endpoint in public_routes:
        return None
    
    # For all other routes, require valid session
    if 'user_id' not in session:
        logger.warning(f"Access denied: No session. Endpoint: {request.endpoint}, IP: {request.remote_addr}")
        flash("❌ Please login to continue.", "error")
        return redirect(url_for('login'))
    
    # Validate session integrity
    if not validate_session():
        logger.warning(f"Access denied: Invalid session. Endpoint: {request.endpoint}, User: {session.get('user_id')}")
        session.clear()
        flash("❌ Your session is invalid. Please login again.", "error")
        return redirect(url_for('login'))
    
    return None


@app.after_request
def after_request(response):
    """
    Add security headers to all responses.
    Prevent caching of sensitive content.
    """
    # Prevent caching for authenticated pages
    if request.endpoint not in ['login', 'static', 'uploaded_file']:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    
    # Security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:; font-src 'self' data:;"
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    return response


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def allowed_file(filename):
    """Check if uploaded file has allowed extension."""
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in config.ALLOWED_EXTENSIONS


def save_file(file_storage):
    """Save uploaded file with unique name."""
    if not file_storage or not file_storage.filename or not allowed_file(file_storage.filename):
        return None

    timestamp = int(datetime.utcnow().timestamp())
    safe_filename = secure_filename(file_storage.filename)
    saved_name = f"{timestamp}_{safe_filename}"

    dest_folder = app.config.get("UPLOAD_FOLDER", config.UPLOAD_FOLDER)
    os.makedirs(dest_folder, exist_ok=True)
    dest_path = os.path.join(dest_folder, saved_name)
    file_storage.save(dest_path)
    
    return saved_name


def convert_to_primary(amount, from_currency, exchange_rate, primary_currency="USD"):
    """Convert amount from one currency to primary currency."""
    try:
        amt = float(amount or 0.0)
    except (TypeError, ValueError):
        amt = 0.0

    from_curr = (from_currency or "USD").upper()
    primary_curr = (primary_currency or "USD").upper()

    if from_curr == primary_curr:
        return amt

    try:
        er = float(exchange_rate)
        if er == 0:
            return 0.0
    except (TypeError, ValueError):
        return 0.0

    if primary_curr == "USD" and from_curr == "CAD":
        return amt / er
    elif primary_curr == "CAD" and from_curr == "USD":
        return amt * er

    return amt


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route("/", methods=["GET", "POST"])
def login():
    """
    Handle user login.
    Clears session when login page is displayed (GET request).
    Authenticates user and creates new session (POST request).
    """
    # Clear session when GET request (page load) to ensure clean slate
    if request.method == "GET":
        session.clear()
        logger.info(f"Login page accessed at {datetime.utcnow()} from {request.remote_addr} - Session cleared")
    
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        
        # Validate form inputs
        if not identifier or not password:
            flash("❌ Please enter both username/email and password.", "error")
            return redirect(url_for('login'))

        # Owner login
        if identifier == config.ADMIN_USERNAME:
            if check_password_hash(config.ADMIN_PASSWORD_HASH, password):
                session.clear()
                session['user_id'] = 'owner'
                session['user_role'] = 'owner'
                session['user_name'] = 'Owner'
                session.permanent = True
                
                logger.info(f"✅ Owner logged in successfully at {datetime.utcnow()}")
                flash("✅ Login successful. Welcome Owner!", "success")
                return redirect(url_for('owner_dashboard'))
            else:
                logger.warning(f"❌ Failed owner login attempt at {datetime.utcnow()} from {request.remote_addr}")
                flash("❌ Invalid owner credentials.", "error")
                return redirect(url_for('login'))

        # Driver login
        email = identifier.lower()
        driver = db.drivers.find_one({"email": email})
        if driver and check_password_hash(driver.get("password_hash", ""), password):
            session.clear()
            session['user_id'] = str(driver['_id'])
            session['user_role'] = 'driver'
            session['user_name'] = driver.get('name')
            session.permanent = True
            
            logger.info(f"✅ Driver {email} logged in successfully at {datetime.utcnow()}")
            flash(f"✅ Login successful. Welcome {driver.get('name')}!", "success")
            return redirect(url_for('driver_dashboard'))

        logger.warning(f"❌ Failed login attempt with identifier: {identifier} at {datetime.utcnow()} from {request.remote_addr}")
        flash("❌ Invalid login credentials.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    """Log out user and clear session."""
    user_name = session.get('user_name', 'User')
    user_id = session.get('user_id', 'Unknown')
    
    logger.info(f"✅ {user_name} ({user_id}) logged out at {datetime.utcnow()}")
    
    session.clear()
    
    response = make_response(redirect(url_for('login')))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    flash("✅ You have been logged out successfully.", "info")
    return response


# ============================================================================
# DASHBOARD ROUTES
# ============================================================================

@app.route("/owner")
@require_owner
def owner_dashboard():
    """Owner's main dashboard - PROTECTED."""
    current_exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()
    trips = db.list_trips()
    units = db.list_units()

    total_revenue_primary = 0.0
    total_expenses_primary = 0.0

    for t in trips:
        rate_for_trip = t.get("exchange_rate_at") if t.get("status") == "completed" and t.get("exchange_rate_at") else current_exchange_rate
        
        payment_usd = t.get("payment_usd", 0) or 0
        total_revenue_primary += convert_to_primary(payment_usd, "USD", rate_for_trip, primary_currency)

        for e in t.get("expenses", []):
            total_expenses_primary += convert_to_primary(e.get("amount", 0), e.get("currency", "USD"), rate_for_trip, primary_currency)

    for u in units:
        for ex in u.get("expenses", []):
            total_expenses_primary += convert_to_primary(ex.get("amount", 0), ex.get("currency", "USD"), current_exchange_rate, primary_currency)

    recent_raw = sorted(trips, key=lambda x: x.get('created_at', datetime.utcnow()), reverse=True)[:10]
    recent_trips = []
    for t in recent_raw:
        rate = t.get("exchange_rate_at") if t.get("status") == "completed" else current_exchange_rate
        payment_primary = convert_to_primary(t.get("payment_usd", 0), "USD", rate, primary_currency)
        expenses_primary = sum(convert_to_primary(e.get("amount", 0), e.get("currency"), rate, primary_currency) for e in t.get("expenses", []))
        driver = db.get_driver(t.get("driver_id")) if t.get("driver_id") else None
        unit = db.get_unit(t.get("unit_id")) if t.get("unit_id") else None

        recent_trips.append({
            "pickup_date": t.get("pickup_date"),
            "trip_number": t.get("trip_number"),
            "driver_name": driver.get("name") if driver else "-",
            "unit_number": unit.get("number") if unit else "-",
            "route": f"{t.get('pickup_city')} → {t.get('delivery_city')}",
            "status": t.get("status"),
            "profit": payment_primary - expenses_primary
        })
    
    stats = {
        "total_trips": len(trips),
        "active_trips": len([t for t in trips if t.get('status') == 'active']),
        "completed_trips": len([t for t in trips if t.get('status') == 'completed']),
        "total_revenue_primary": total_revenue_primary,
        "total_expenses_primary": total_expenses_primary,
        "net_primary": total_revenue_primary - total_expenses_primary,
        "primary_currency": primary_currency
    }

    return render_template("owner_dashboard.html", stats=stats, recent_trips=recent_trips)


@app.route("/driver")
@require_driver
def driver_dashboard():
    """Driver's dashboard - PROTECTED."""
    driver_id = session.get('user_id')
    trips = db.list_trips({"driver_id": ObjectId(driver_id)}) if driver_id else []
    
    for t in trips:
        t['_id'] = str(t['_id'])
        
    return render_template("driver_dashboard.html", trips=trips)


# ============================================================================
# TRIP MANAGEMENT ROUTES
# ============================================================================

@app.route("/trips")
@require_owner
def all_trips():
    """List all trips - OWNER ONLY."""
    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()
    
    trips_processed = []
    for t in db.list_trips():
        rate = t.get("exchange_rate_at") if t.get("status") == "completed" else exchange_rate
        payment_primary = convert_to_primary(t.get("payment_usd", 0), "USD", rate, primary_currency)
        expenses_primary = sum(convert_to_primary(e.get("amount", 0), e.get("currency"), rate, primary_currency) for e in t.get("expenses", []))
        
        driver = db.get_driver(t.get("driver_id")) if t.get("driver_id") else None
        unit = db.get_unit(t.get("unit_id")) if t.get("unit_id") else None

        trips_processed.append({
            **t,
            "_id": str(t["_id"]),
            "driver_name": driver.get("name") if driver else "-",
            "unit_number": unit.get("number") if unit else "-",
            "payment_primary": payment_primary,
            "expenses_primary": expenses_primary,
            "profit_primary": payment_primary - expenses_primary,
        })
        
    return render_template("all_trips.html", trips=trips_processed, primary_currency=primary_currency)


@app.route("/trips/new", methods=["GET", "POST"])
@require_owner
def new_trip():
    """Create new trip - OWNER ONLY."""
    if request.method == "POST":
        payment_amount = float(request.form.get("payment_amount") or 0)
        payment_currency = request.form.get("payment_currency", "USD")
        
        if payment_currency == "CAD":
            exchange_rate = db.get_exchange_rate()
            payment_usd = payment_amount / exchange_rate
        else:
            payment_usd = payment_amount
        
        trip_doc = {
            "trip_number": request.form.get("trip_number"),
            "driver_id": ObjectId(request.form.get("driver_id")) if request.form.get("driver_id") else None,
            "unit_id": ObjectId(request.form.get("unit_id")) if request.form.get("unit_id") else None,
            "pickup_date": request.form.get("pickup_date"),
            "delivery_date": request.form.get("delivery_date"),
            "pickup_city": request.form.get("pickup_city"),
            "delivery_city": request.form.get("delivery_city"),
            "payment_usd": payment_usd,
            "status": request.form.get("status", "active"),
            "expenses": [],
            "created_at": datetime.utcnow()
        }
        db.create_trip(trip_doc)
        flash("✅ Trip created successfully.", "success")
        return redirect(url_for('all_trips'))

    drivers = list(db.drivers.find())
    units = list(db.units.find())
    default_trip_number = "T" + datetime.utcnow().strftime("%Y%m%d%H%M")
    live_exchange_rate = ExchangeRateService.get_live_rate()
    
    return render_template("new_trip.html", 
                          drivers=drivers, 
                          units=units, 
                          default_trip_number=default_trip_number,
                          live_exchange_rate=live_exchange_rate)


@app.route("/trips/<trip_id>")
@require_login
def trip_detail(trip_id):
    """View trip details - LOGIN REQUIRED."""
    trip = db.get_trip(trip_id)
    if not trip:
        flash("❌ Trip not found.", "error")
        return redirect(url_for('all_trips') if session.get('user_role') == 'owner' else url_for('driver_dashboard'))

    # Permission check for adding expenses
    can_add_expense = False
    if session.get('user_role') == 'owner':
        can_add_expense = True
    elif session.get('user_role') == 'driver' and str(trip.get("driver_id")) == session.get('user_id'):
        if trip.get('status') != 'completed':
            can_add_expense = True
        else:
            completed_at = trip.get('completed_at')
            if completed_at and (datetime.utcnow() - completed_at) <= timedelta(hours=24):
                can_add_expense = True
    
    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()
    rate_for_trip = trip.get("exchange_rate_at") or exchange_rate
    locked_rate = trip.get("exchange_rate_at")

    expenses_display = []
    for e in trip.get("expenses", []):
        expenses_display.append({
            **e,
            "original_amount": e.get("amount", 0),
            "original_currency": e.get("currency", "USD"),
            "converted_amount": convert_to_primary(e.get("amount", 0), e.get("currency"), rate_for_trip, primary_currency),
            "created_at": e.get("created_at").strftime("%Y-%m-%d %H:%M") if isinstance(e.get("created_at"), datetime) else ""
        })

    payment_primary = convert_to_primary(trip.get("payment_usd", 0), "USD", rate_for_trip, primary_currency)
    total_expenses_primary = sum(item["converted_amount"] for item in expenses_display)
    profit_primary = payment_primary - total_expenses_primary
    
    driver = db.get_driver(trip.get("driver_id"))
    unit = db.get_unit(trip.get("unit_id"))
    
    return render_template("trip_detail.html", 
                          trip=trip, 
                          driver=driver, 
                          unit=unit,
                          can_add_expense=can_add_expense, 
                          is_owner=(session.get('user_role')=='owner'),
                          primary_currency=primary_currency, 
                          expenses_display=expenses_display,
                          payment_primary=payment_primary, 
                          total_expenses_primary=total_expenses_primary,
                          profit_primary=profit_primary,
                          locked_rate=locked_rate,
                          current_rate=exchange_rate)


@app.route("/trips/<trip_id>/add-expense", methods=["POST"])
@require_login
def add_expense(trip_id):
    """Add expense to trip - LOGIN REQUIRED."""
    trip = db.get_trip(trip_id)
    if not trip:
        flash("❌ Trip not found.", "error")
        return redirect(url_for('all_trips'))

    is_allowed = False
    if session.get('user_role') == 'owner': 
        is_allowed = True
    elif session.get('user_role') == 'driver' and str(trip.get("driver_id")) == session.get('user_id'):
        if trip.get('status') != 'completed' or (trip.get('completed_at') and datetime.utcnow() - trip.get('completed_at') <= timedelta(hours=24)):
            is_allowed = True

    if not is_allowed:
        logger.warning(f"Unauthorized expense add attempt by {session.get('user_id')} for trip {trip_id}")
        flash("❌ You are not allowed to add expenses to this trip at this time.", "error")
        return redirect(url_for('trip_detail', trip_id=trip_id))

    expense_doc = {
        "category": request.form.get("category"),
        "amount": float(request.form.get("amount") or 0),
        "currency": request.form.get("currency", "USD"),
        "description": request.form.get("description"),
        "receipt": save_file(request.files.get("receipt")),
        "created_at": datetime.utcnow()
    }
    db.add_trip_expense(trip_id, expense_doc)
    flash("✅ Expense added successfully.", "success")
    return redirect(url_for('trip_detail', trip_id=trip_id))


@app.route("/trips/<trip_id>/mark-complete", methods=["POST"])
@require_owner
def mark_complete(trip_id):
    """Mark trip as completed - OWNER ONLY."""
    live_rate = ExchangeRateService.get_live_rate()
    
    update_fields = {
        "status": "completed",
        "completed_at": datetime.utcnow(),
        "exchange_rate_at": live_rate
    }
    db.update_trip(trip_id, update_fields)
    logger.info(f"Trip {trip_id} marked as completed by owner")
    flash(f"✅ Trip marked as completed. Exchange rate locked at 1 USD = {live_rate:.4f} CAD.", "success")
    return redirect(url_for('trip_detail', trip_id=trip_id))


@app.route("/driver/trips/<trip_id>/complete", methods=["POST"])
@require_driver
def driver_mark_complete(trip_id):
    """Driver marks trip as completed - DRIVER ONLY."""
    trip = db.get_trip(trip_id)
    if not trip or str(trip.get("driver_id")) != session.get('user_id'):
        logger.warning(f"Driver {session.get('user_id')} tried to complete unauthorized trip {trip_id}")
        flash("❌ Trip not found or not assigned to you.", "error")
        return redirect(url_for('driver_dashboard'))
    
    live_rate = ExchangeRateService.get_live_rate()
    
    update_fields = {
        "status": "completed",
        "completed_at": datetime.utcnow(),
        "exchange_rate_at": live_rate
    }
    db.update_trip(trip_id, update_fields)
    logger.info(f"Trip {trip_id} marked as completed by driver {session.get('user_id')}")
    flash(f"✅ Trip marked as completed. Exchange rate locked at 1 USD = {live_rate:.4f} CAD.", "info")
    return redirect(url_for('trip_detail', trip_id=trip_id))


# ============================================================================
# DRIVER MANAGEMENT ROUTES
# ============================================================================

@app.route("/drivers")
@require_owner
def drivers():
    """List all drivers - OWNER ONLY."""
    drivers_list = list(db.drivers.find())
    for d in drivers_list:
        d['trips_count'] = db.trips.count_documents({"driver_id": d.get('_id')})
        d['_id'] = str(d['_id'])
        
    return render_template("drivers.html", drivers=drivers_list)


@app.route("/drivers/new", methods=["GET", "POST"])
@require_owner
def new_driver():
    """Create new driver - OWNER ONLY."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if db.drivers.find_one({"email": email}):
            flash("❌ A driver with this email already exists.", "error")
            return redirect(url_for('drivers'))

        full_name = f'{request.form.get("first_name", "").strip()} {request.form.get("last_name", "").strip()}'.strip()
        password = request.form.get("password", "").strip()

        if not all([full_name, email, password]):
            flash("❌ First name, email, and password are required.", "error")
            return redirect(url_for('new_driver'))
            
        driver_doc = {
            "name": full_name,
            "email": email,
            "phone": request.form.get("phone", "").strip(),
            "id_number": request.form.get("id_number", "").strip(),
            "driving_license": request.form.get("driving_license", "").strip(),
            "photo": save_file(request.files.get("photo")),
            "password_hash": generate_password_hash(password),
            "created_at": datetime.utcnow()
        }
        db.create_driver(driver_doc)
        logger.info(f"New driver created: {email}")
        flash("✅ Driver created successfully.", "success")
        return render_template("driver_created.html", name=full_name, email=email, password=password)

    return render_template("new_driver.html")


@app.route("/drivers/<driver_id>")
@require_login
def driver_profile(driver_id):
    """View driver profile - LOGIN REQUIRED."""
    if session.get('user_role') == 'driver' and session.get('user_id') != driver_id:
        logger.warning(f"Driver {session.get('user_id')} tried to access profile of {driver_id}")
        flash("❌ You are not authorized to view this profile.", "error")
        return redirect(url_for('driver_dashboard'))
        
    driver = db.get_driver(driver_id)
    if not driver:
        flash("❌ Driver not found.", "error")
        return redirect(url_for('drivers') if session.get('user_role') == 'owner' else url_for('driver_dashboard'))
    
    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()
    driver_trips = list(db.trips.find({"driver_id": ObjectId(driver_id)}))

    revenue_primary = 0.0
    for t in driver_trips:
        rate = t.get("exchange_rate_at") if t.get("status") == "completed" else exchange_rate
        revenue_primary += convert_to_primary(t.get("payment_usd", 0), "USD", rate, primary_currency)

    trips_display = []
    for t in driver_trips:
        rate = t.get("exchange_rate_at") if t.get("status") == "completed" else exchange_rate
        payment_primary = convert_to_primary(t.get("payment_usd", 0), "USD", rate, primary_currency)
        expenses_primary = sum(convert_to_primary(e.get("amount", 0), e.get("currency"), rate, primary_currency) for e in t.get("expenses", []))
        
        trips_display.append({
            "_id": str(t['_id']), "trip_number": t.get("trip_number"),
            "pickup_date": t.get("pickup_date"), "delivery_date": t.get("delivery_date"),
            "route": f"{t.get('pickup_city')} → {t.get('delivery_city')}",
            "status": t.get("status"), "payment_primary": payment_primary,
            "expenses_primary": expenses_primary, "profit_primary": payment_primary - expenses_primary
        })
        
    return render_template("driver_profile.html", driver=driver,
                           total_trips=len(driver_trips), revenue_primary=revenue_primary,
                           trips=trips_display, primary_currency=primary_currency)


# ============================================================================
# UNIT MANAGEMENT ROUTES
# ============================================================================

@app.route("/units")
@require_owner
def units():
    """List all units - OWNER ONLY."""
    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()
    
    units_list = list(db.units.find())
    for u in units_list:
        total_expenses_primary = sum(convert_to_primary(
            exp.get('amount', 0), exp.get('currency'), exchange_rate, primary_currency
        ) for exp in u.get('expenses', []))
        u['total_expenses_primary'] = total_expenses_primary
        u['_id'] = str(u['_id'])

    return render_template("units.html", units=units_list, primary_currency=primary_currency)


@app.route("/units/new", methods=["GET", "POST"])
@require_owner
def new_unit():
    """Create new unit - OWNER ONLY."""
    if request.method == "POST":
        unit_doc = {
            "number": request.form.get("number"),
            "make": request.form.get("make"),
            "model": request.form.get("model"),
            "expenses": [],
            "created_at": datetime.utcnow()
        }
        db.create_unit(unit_doc)
        logger.info(f"New unit created: {request.form.get('number')}")
        flash("✅ Unit created successfully.", "success")
        return redirect(url_for('units'))
        
    return render_template("new_unit.html")


@app.route("/units/<unit_id>")
@require_login
def unit_detail(unit_id):
    """View unit details - LOGIN REQUIRED."""
    unit = db.get_unit(unit_id)
    if not unit:
        flash("❌ Unit not found.", "error")
        return redirect(url_for('units'))

    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()

    unit_expenses_primary = sum(convert_to_primary(ex.get("amount", 0), ex.get("currency"), exchange_rate, primary_currency) for ex in unit.get("expenses", []))

    revenue_primary = 0.0
    for t in db.list_trips({"unit_id": ObjectId(unit_id)}):
        rate = t.get("exchange_rate_at") if t.get("status") == "completed" else exchange_rate
        revenue_primary += convert_to_primary(t.get("payment_usd", 0), "USD", rate, primary_currency)

    for e in unit.get('expenses', []):
        if isinstance(e.get('created_at'), datetime):
            e['created_at'] = e['created_at'].strftime("%Y-%m-%d %H:%M")
            
    return render_template("unit_detail.html", unit=unit,
                           primary_currency=primary_currency,
                           unit_expenses_primary=unit_expenses_primary,
                           revenue_primary=revenue_primary)


@app.route("/units/<unit_id>/add-expense", methods=["POST"])
@require_owner
def add_unit_expense(unit_id):
    """Add expense to unit - OWNER ONLY."""
    expense_doc = {
        "category": request.form.get("category", "").strip(),
        "amount": float(request.form.get("amount") or 0),
        "currency": request.form.get("currency", "USD").upper(),
        "description": request.form.get("description", "").strip(),
        "receipt": save_file(request.files.get("receipt")),
        "created_at": datetime.utcnow()
    }
    db.add_unit_expense(unit_id, expense_doc)
    flash("✅ Unit expense added successfully.", "success")
    return redirect(url_for('unit_detail', unit_id=unit_id))


# ============================================================================
# SYSTEM ROUTES
# ============================================================================

@app.route("/set_primary_currency", methods=["POST"])
@require_owner
def set_primary_currency():
    """Set primary currency - OWNER ONLY."""
    cur = request.form.get("primary_currency", "USD")
    if cur not in ("USD", "CAD"): 
        cur = "USD"
    db.set_primary_currency(cur)
    logger.info(f"Primary currency changed to {cur}")
    flash(f"✅ Primary currency has been set to {cur}.", "success")
    return redirect(url_for('owner_dashboard'))


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """Serve uploaded files."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    logger.warning(f"404 Error: {request.path} - {request.remote_addr}")
    flash("❌ Page not found.", "error")
    if 'user_id' in session:
        return redirect(url_for('owner_dashboard') if session.get('user_role') == 'owner' else url_for('driver_dashboard'))
    return redirect(url_for('login'))


@app.errorhandler(403)
def forbidden(error):
    """Handle 403 errors."""
    logger.warning(f"403 Forbidden: {request.path} - {request.remote_addr}")
    flash("❌ Access denied.", "error")
    return redirect(url_for('login'))


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"500 Error: {str(error)}")
    flash("❌ An unexpected error occurred. Please try again.", "error")
    return redirect(url_for('login'))


# ============================================================================
# APPLICATION EXECUTION
# ============================================================================

if __name__ == "__main__":
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))