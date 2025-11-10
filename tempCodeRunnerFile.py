# Updated app.py with:
# - primary-currency summaries (convert amounts to primary currency)
# - lock exchange rate when trip is completed (exchange_rate_at stored on trip)
# - driver profile view with totals and trips list
# - unit summary including revenue by unit and aggregated expenses in primary currency
# - conversions: usd_from_amount + convert_to_primary helpers
# - ensure endpoints names match templates (add_unit_expense)
# - Added categories to flash messages for toast notifications
#
# NOTE: This file assumes db_handler.py provides DBHandler with same API as before.

import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from bson.objectid import ObjectId
import config
from db_handler import DBHandler

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
db = DBHandler()

# -----------------------
# Helpers
# -----------------------
def allowed_file(filename):
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in getattr(config, "ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "gif", "pdf"})

def save_file(file_storage):
    if not file_storage:
        return None
    filename = getattr(file_storage, "filename", "")
    if not filename:
        return None
    if not allowed_file(filename):
        return None
    timestamp = int(datetime.utcnow().timestamp())
    safe = secure_filename(filename)
    saved_name = f"{timestamp}_{safe}"
    dest_folder = app.config.get("UPLOAD_FOLDER", config.UPLOAD_FOLDER)
    os.makedirs(dest_folder, exist_ok=True)
    dest_path = os.path.join(dest_folder, saved_name)
    file_storage.save(dest_path)
    return saved_name

def usd_from_amount(amount, currency, exchange_rate):
    try:
        amt = float(amount or 0)
    except (TypeError, ValueError):
        amt = 0.0
    if not currency:
        currency = "USD"
    currency = currency.upper()
    if currency == "USD":
        return amt
    if currency == "CAD":
        try:
            er = float(exchange_rate)
            return amt / er if er != 0 else 0.0
        except (TypeError, ValueError):
            return 0.0
    return amt

def convert_to_primary(amount, from_currency, exchange_rate, primary_currency="USD"):
    """
    Convert amount that is in from_currency into primary_currency using exchange_rate.
    exchange_rate: USD -> CAD (i.e., 1 USD = exchange_rate CAD)
    """
    if amount is None:
        return 0.0
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        amt = 0.0
    from_currency = (from_currency or "USD").upper()
    primary = (primary_currency or "USD").upper()
    # if same currency, no conversion
    if from_currency == primary:
        return amt
    # if primary is USD and source is CAD: CAD -> USD = amount / exchange_rate
    if primary == "USD" and from_currency == "CAD":
        try:
            er = float(exchange_rate)
            return amt / er if er != 0 else 0.0
        except Exception:
            return 0.0
    # if primary is CAD and source is USD: USD -> CAD = amount * exchange_rate
    if primary == "CAD" and from_currency == "USD":
        try:
            er = float(exchange_rate)
            return amt * er
        except Exception:
            return 0.0
    # unknown path: return as-is
    return amt

# -----------------------
# Authentication & login
# -----------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form["identifier"].strip()
        password = request.form["password"]
        # Owner login if identifier matches ADMIN_USERNAME
        if identifier == config.ADMIN_USERNAME:
            if check_password_hash(config.ADMIN_PASSWORD_HASH, password):
                session['user_id'] = 'owner'
                session['user_role'] = 'owner'
                session['user_name'] = 'Owner'
                flash("Login successful", "success")
                return redirect(url_for('owner_dashboard'))
            else:
                flash("Invalid owner credentials", "error")
                return redirect(url_for('login'))
        # Driver login
        email = identifier.lower()
        driver = db.drivers.find_one({"email": email})
        if driver and check_password_hash(driver.get("password_hash", ""), password):
            session['user_id'] = str(driver['_id'])
            session['user_role'] = 'driver'
            session['user_name'] = driver.get('name')
            flash("Login successful", "success")
            return redirect(url_for('driver_dashboard'))
        flash("Invalid login credentials", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# -----------------------
# Owner Dashboard + settings
# -----------------------
@app.route("/owner")
def owner_dashboard():
    if session.get('user_role') != 'owner':
        flash("Access denied.", "error")
        return redirect(url_for('login'))

    current_exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()

    trips = db.list_trips()
    units = db.list_units()

    # totals in primary currency
    total_trips = len(trips)
    active_trips = len([t for t in trips if t.get('status') == 'active'])
    completed_trips = len([t for t in trips if t.get('status') == 'completed'])

    total_revenue_primary = 0.0
    total_expenses_primary = 0.0

    # revenue: for each trip, convert trip.payment_usd (stored as USD) to primary currency
    for t in trips:
        # determine rate to use: if trip has exchange_rate_at (locked at completion) and trip is completed, use that
        rate_for_trip = t.get("exchange_rate_at") if t.get("status") == "completed" and t.get("exchange_rate_at") else current_exchange_rate
        # trip stores payment_usd; convert to primary currency
        payment_usd = t.get("payment_usd", 0) or 0
        payment_in_primary = convert_to_primary(payment_usd, "USD", rate_for_trip, primary_currency)
        total_revenue_primary += payment_in_primary

        # trip expenses converted to primary using same rate_for_trip
        for e in t.get("expenses", []):
            total_expenses_primary += convert_to_primary(e.get("amount", 0), e.get("currency", "USD"), rate_for_trip, primary_currency)

    # include unit expenses aggregated (each unit has expenses in original currencies)
    for u in units:
        for ex in u.get("expenses", []):
            # When unit expenses were created, they didn't lock to a trip rate; we treat them as current unless you want a per-expense locked rate
            total_expenses_primary += convert_to_primary(ex.get("amount", 0), ex.get("currency", "USD"), current_exchange_rate, primary_currency)

    net_primary = total_revenue_primary - total_expenses_primary

    # recent trips for display (use primary currency profit for each)
    recent_raw = sorted(trips, key=lambda x: x.get('created_at', datetime.utcnow()), reverse=True)[:10]
    recent_trips = []
    for t in recent_raw:
        rate_for_trip = t.get("exchange_rate_at") if t.get("status") == "completed" and t.get("exchange_rate_at") else current_exchange_rate
        expenses_primary = sum(convert_to_primary(e.get("amount", 0), e.get("currency", "USD"), rate_for_trip, primary_currency) for e in t.get("expenses", []))
        payment_primary = convert_to_primary(t.get("payment_usd", 0) or 0, "USD", rate_for_trip, primary_currency)
        profit_primary = payment_primary - expenses_primary
        driver = db.drivers.find_one({"_id": t.get("driver_id")}) if t.get("driver_id") else None
        unit = db.units.find_one({"_id": t.get("unit_id")}) if t.get("unit_id") else None
        recent_trips.append({
            "pickup_date": t.get("pickup_date"),
            "trip_number": t.get("trip_number"),
            "driver_name": driver.get("name") if driver else None,
            "unit_number": unit.get("number") if unit else None,
            "route": f"{t.get('pickup_city')} → {t.get('delivery_city')}",
            "status": t.get("status"),
            "profit": profit_primary
        })

    stats = {
        "total_trips": total_trips,
        "active_trips": active_trips,
        "completed_trips": completed_trips,
        "total_revenue_primary": total_revenue_primary,
        "total_expenses_primary": total_expenses_primary,
        "net_primary": net_primary,
        "primary_currency": primary_currency
    }

    return render_template("owner_dashboard.html",
                           exchange_rate=current_exchange_rate,
                           stats=stats,
                           recent_trips=recent_trips)

@app.route("/set_primary_currency", methods=["POST"])
def set_primary_currency():
    if session.get('user_role') != 'owner':
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    cur = request.form.get("primary_currency", "USD")
    if cur not in ("USD", "CAD"):
        cur = "USD"
    db.set_primary_currency(cur)
    flash(f"Primary currency set to {cur}", "success")
    return redirect(url_for('owner_dashboard'))

@app.route("/update-exchange-rate", methods=["POST"])
def update_exchange_rate():
    if session.get('user_role') != 'owner':
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    rate = float(request.form.get("exchange_rate", config.DEFAULT_EXCHANGE_RATE))
    db.set_exchange_rate(rate)
    flash("Exchange rate updated", "success")
    return redirect(url_for('owner_dashboard'))

# -----------------------
# Units: list, create, detail, add expense
# -----------------------
@app.route("/units")
def units():
    if session.get('user_role') != 'owner':
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    
    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()
    
    units_list = list(db.units.find())
    for u in units_list:
        u['_id'] = str(u['_id'])
        # Calculate total expenses in primary currency for each unit
        total_expenses_primary = 0.0
        for expense in u.get('expenses', []):
            total_expenses_primary += convert_to_primary(
                expense.get('amount', 0),
                expense.get('currency'),
                exchange_rate,
                primary_currency
            )
        u['total_expenses_primary'] = total_expenses_primary

    return render_template("units.html", units=units_list, primary_currency=primary_currency)

@app.route("/units/new", methods=["GET", "POST"])
def new_unit():
    if session.get('user_role') != 'owner':
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    if request.method == "POST":
        doc = {"number": request.form.get("number"), "make": request.form.get("make"),
               "model": request.form.get("model"), "expenses": [], "created_at": datetime.utcnow()}
        db.create_unit(doc)
        flash("Unit created successfully", "success")
        return redirect(url_for('units'))
    return render_template("new_unit.html")

@app.route("/units/<unit_id>")
def unit_detail(unit_id):
    if session.get('user_role') not in ('owner', 'driver'):
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    unit = db.units.find_one({"_id": ObjectId(unit_id)})
    if not unit:
        flash("Unit not found", "error")
        return redirect(url_for('units'))
    # format dates
    for e in unit.get('expenses', []):
        if isinstance(e.get('created_at'), datetime):
            e['created_at'] = e['created_at'].strftime("%Y-%m-%d %H:%M")
    unit['_id'] = str(unit['_id'])
    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()

    # aggregated totals for this unit in primary currency
    unit_expenses_primary = sum(convert_to_primary(ex.get("amount", 0), ex.get("currency", "USD"), exchange_rate, primary_currency) for ex in unit.get("expenses", []))

    # revenue generated by unit from trips
    trips_for_unit = db.list_trips({"unit_id": ObjectId(unit_id)}) if isinstance(ObjectId(unit_id), ObjectId) else db.list_trips({"unit_id": ObjectId(unit_id)})
    revenue_primary = 0.0
    for t in trips_for_unit:
        rate_for_trip = t.get("exchange_rate_at") if t.get("status") == "completed" and t.get("exchange_rate_at") else exchange_rate
        revenue_primary += convert_to_primary(t.get("payment_usd", 0) or 0, "USD", rate_for_trip, primary_currency)

    return render_template("unit_detail.html", unit=unit, exchange_rate=exchange_rate,
                           primary_currency=primary_currency, unit_expenses_primary=unit_expenses_primary,
                           revenue_primary=revenue_primary)

@app.route("/units/<unit_id>/add-expense", methods=["POST"], endpoint="add_unit_expense")
def add_unit_expense(unit_id):
    if session.get('user_role') != 'owner':
        flash("Only owner can add unit expenses", "error")
        return redirect(url_for('login'))
    unit = db.units.find_one({"_id": ObjectId(unit_id)})
    if not unit:
        flash("Unit not found", "error")
        return redirect(url_for('units'))
    category = request.form.get("category", "").strip()
    amount = float(request.form.get("amount") or 0)
    currency = request.form.get("currency", "USD").upper()
    description = request.form.get("description", "").strip()
    receipt_file = request.files.get("receipt")
    receipt_filename = save_file(receipt_file)
    expense = {"category": category, "amount": amount, "currency": currency, "description": description,
               "receipt": receipt_filename, "created_at": datetime.utcnow()}
    db.add_unit_expense(unit_id, expense)
    flash("Unit expense added", "success")
    return redirect(url_for('unit_detail', unit_id=unit_id))

# -----------------------
# Drivers management & profile
# -----------------------
@app.route("/drivers")
def drivers():
    if session.get('user_role') != 'owner':
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    drivers = list(db.drivers.find())
    counts = {}
    for d in drivers:
        counts[str(d['_id'])] = len(list(db.trips.find({"driver_id": d.get('_id')})))
        d['_id'] = str(d['_id'])
    return render_template("drivers.html", drivers=drivers, drivers_trips_count=counts)

@app.route("/drivers/new", methods=["GET", "POST"])
def new_driver():
    if session.get('user_role') != 'owner':
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        full_name = (first_name + " " + last_name).strip() if first_name else request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        id_number = request.form.get("id_number", "").strip()
        driving_license = request.form.get("driving_license", "").strip()
        password = request.form.get("password", "").strip()
        photo = request.files.get("photo")
        photo_filename = save_file(photo)
        if not full_name or not email or not password:
            flash("Name, email and password are required", "error")
            return redirect(url_for('new_driver'))
        existing = db.drivers.find_one({"email": email})
        if existing:
            flash("Driver with this email already exists", "error")
            return redirect(url_for('drivers'))
        password_hash = generate_password_hash(password)
        driver_doc = {"name": full_name, "first_name": first_name, "last_name": last_name,
                      "email": email, "phone": phone, "id_number": id_number,
                      "driving_license": driving_license, "photo": photo_filename,
                      "password_hash": password_hash, "created_at": datetime.utcnow()}
        db.create_driver(driver_doc)
        flash("Driver created successfully", "success")
        return render_template("driver_created.html", name=full_name, email=email, password=password)
    return render_template("new_driver.html")

@app.route("/drivers/<driver_id>")
def driver_profile(driver_id):
    # both owner and driver can view driver profile; driver can view their own profile
    if session.get('user_role') not in ('owner', 'driver'):
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    # drivers can only view their own unless owner
    if session.get('user_role') == 'driver' and session.get('user_id') != str(driver_id):
        # allow if they view their own by id (string matching)
        # otherwise redirect
        if session.get('user_id') != str(driver_id):
            flash("Unauthorized to view this profile", "error")
            return redirect(url_for('driver_dashboard'))
    driver = db.drivers.find_one({"_id": ObjectId(driver_id)})
    if not driver:
        flash("Driver not found", "error")
        return redirect(url_for('drivers') if session.get('user_role') == 'owner' else url_for('driver_dashboard'))
    # compute stats
    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()

    driver_trips = list(db.trips.find({"driver_id": ObjectId(driver_id)}))
    total_trips = len(driver_trips)
    revenue_primary = 0.0
    for t in driver_trips:
        rate_for_trip = t.get("exchange_rate_at") if t.get("status") == "completed" and t.get("exchange_rate_at") else exchange_rate
        revenue_primary += convert_to_primary(t.get("payment_usd", 0) or 0, "USD", rate_for_trip, primary_currency)

    # format trips for display
    trips_display = []
    for t in driver_trips:
        t_id = str(t['_id'])
        rate_for_trip = t.get("exchange_rate_at") if t.get("status") == "completed" and t.get("exchange_rate_at") else exchange_rate
        expenses_primary = sum(convert_to_primary(e.get("amount", 0), e.get("currency", "USD"), rate_for_trip, primary_currency) for e in t.get("expenses", []))
        payment_primary = convert_to_primary(t.get("payment_usd", 0) or 0, "USD", rate_for_trip, primary_currency)
        trips_display.append({
            "_id": t_id,
            "trip_number": t.get("trip_number"),
            "pickup_date": t.get("pickup_date"),
            "delivery_date": t.get("delivery_date"),
            "route": f"{t.get('pickup_city')} → {t.get('delivery_city')}",
            "status": t.get("status"),
            "payment_primary": payment_primary,
            "expenses_primary": expenses_primary,
            "profit_primary": payment_primary - expenses_primary
        })
    # convert driver id for template
    driver['_id'] = str(driver['_id'])
    return render_template("driver_profile.html", driver=driver, total_trips=total_trips,
                           revenue_primary=revenue_primary, trips=trips_display,
                           primary_currency=primary_currency)

# -----------------------
# Trips: list, create, detail, add expense, mark complete
# -----------------------
@app.route("/trips")
def all_trips():
    if session.get('user_role') != 'owner':
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()
    trips_raw = db.list_trips()
    trips = []
    for t in trips_raw:
        rate_for_trip = t.get("exchange_rate_at") if t.get("status") == "completed" and t.get("exchange_rate_at") else exchange_rate
        expenses_primary = sum(convert_to_primary(e.get("amount", 0), e.get("currency", "USD"), rate_for_trip, primary_currency) for e in t.get('expenses', []))
        driver = db.drivers.find_one({"_id": t.get("driver_id")}) if t.get("driver_id") else None
        unit = db.units.find_one({"_id": t.get("unit_id")}) if t.get("unit_id") else None
        t['_id'] = str(t['_id'])
        trips.append({
            **t,
            "driver_name": driver.get("name") if driver else None,
            "unit_number": unit.get("number") if unit else None,
            "expenses_primary": expenses_primary,
            "payment_primary": convert_to_primary(t.get("payment_usd", 0) or 0, "USD", rate_for_trip, primary_currency),
            "profit_primary": convert_to_primary(t.get("payment_usd", 0) or 0, "USD", rate_for_trip, primary_currency) - expenses_primary
        })
    return render_template("all_trips.html", trips=trips, primary_currency=primary_currency)

@app.route("/trips/new", methods=["GET", "POST"])
def new_trip():
    if session.get('user_role') != 'owner':
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    if request.method == "POST":
        trip_doc = {"trip_number": request.form.get("trip_number"),
                    "driver_id": ObjectId(request.form.get("driver_id")) if request.form.get("driver_id") else None,
                    "unit_id": ObjectId(request.form.get("unit_id")) if request.form.get("unit_id") else None,
                    "pickup_date": request.form.get("pickup_date"),
                    "delivery_date": request.form.get("delivery_date"),
                    "pickup_city": request.form.get("pickup_city"),
                    "pickup_state": request.form.get("pickup_state"),
                    "delivery_city": request.form.get("delivery_city"),
                    "delivery_state": request.form.get("delivery_state"),
                    "payment_usd": float(request.form.get("payment_usd") or 0),
                    "payment_cad": float(request.form.get("payment_cad") or 0),
                    "status": request.form.get("status", "active"),
                    "expenses": [], "created_at": datetime.utcnow()}
        db.create_trip(trip_doc)
        flash("Trip created successfully", "success")
        return redirect(url_for('all_trips'))
    drivers = list(db.drivers.find())
    units = list(db.units.find())
    for d in drivers: d['_id'] = str(d['_id'])
    for u in units: u['_id'] = str(u['_id'])
    default_trip_number = "T" + datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return render_template("new_trip.html", drivers=drivers, units=units, default_trip_number=default_trip_number)

@app.route("/trips/<trip_id>", methods=["GET"])
def trip_detail(trip_id):
    trip = db.get_trip(trip_id)
    if not trip:
        flash("Trip not found", "error")
        return redirect(url_for('all_trips') if session.get('user_role')=='owner' else url_for('driver_dashboard'))
    driver = db.drivers.find_one({"_id": trip.get("driver_id")}) if trip.get("driver_id") else None
    unit = db.units.find_one({"_id": trip.get("unit_id")}) if trip.get("unit_id") else None

    # permission for adding expense
    can_add = False
    if session.get('user_role') == 'owner':
        can_add = True
    elif session.get('user_role') == 'driver' and session.get('user_id'):
        if str(trip.get("driver_id")) == session.get('user_id'):
            if trip.get('status') != 'completed':
                can_add = True
            else:
                completed_at = trip.get('completed_at')
                if completed_at:
                    if isinstance(completed_at, datetime):
                        comp_time = completed_at
                    else:
                        try:
                            comp_time = datetime.fromisoformat(completed_at)
                        except Exception:
                            comp_time = None
                    if comp_time and datetime.utcnow() - comp_time <= timedelta(hours=24):
                        can_add = True

    # format each expense and show original + converted-to-primary
    exchange_rate = db.get_exchange_rate()
    primary_currency = db.get_primary_currency()
    rate_for_trip = trip.get("exchange_rate_at") if trip.get("status") == "completed" and trip.get("exchange_rate_at") else exchange_rate

    expenses_display = []
    for e in trip.get("expenses", []):
        original_amount = e.get("amount", 0)
        original_currency = e.get("currency", "USD")
        converted = convert_to_primary(original_amount, original_currency, rate_for_trip, primary_currency)
        rec = {
            "category": e.get("category"),
            "description": e.get("description"),
            "original_amount": original_amount,
            "original_currency": original_currency,
            "converted_amount": converted,
            "receipt": e.get("receipt"),
            "created_at": e.get("created_at").strftime("%Y-%m-%d %H:%M") if isinstance(e.get("created_at"), datetime) else str(e.get("created_at", ""))
        }
        expenses_display.append(rec)

    payment_primary = convert_to_primary(trip.get("payment_usd", 0) or 0, "USD", rate_for_trip, primary_currency)
    total_expenses_primary = sum(item["converted_amount"] for item in expenses_display)
    profit_primary = payment_primary - total_expenses_primary

    trip['_id'] = str(trip['_id'])
    return render_template("trip_detail.html", trip=trip, driver=driver, unit=unit,
                           can_add_expense=can_add, is_owner=(session.get('user_role')=='owner'),
                           exchange_rate=exchange_rate, primary_currency=primary_currency,
                           expenses_display=expenses_display, payment_primary=payment_primary,
                           total_expenses_primary=total_expenses_primary, profit_primary=profit_primary,
                           rate_for_trip=rate_for_trip)

@app.route("/trips/<trip_id>/add-expense", methods=["POST"])
def add_expense(trip_id):
    trip = db.get_trip(trip_id)
    if not trip:
        flash("Trip not found", "error")
        return redirect(url_for('all_trips'))
    allowed = False
    if session.get('user_role') == 'owner':
        allowed = True
    elif session.get('user_role') == 'driver':
        if str(trip.get("driver_id")) == session.get('user_id'):
            if trip.get('status') != 'completed':
                allowed = True
            else:
                completed_at = trip.get('completed_at')
                if completed_at:
                    if isinstance(completed_at, datetime):
                        comp_time = completed_at
                    else:
                        try:
                            comp_time = datetime.fromisoformat(completed_at)
                        except Exception:
                            comp_time = None
                    if comp_time and datetime.utcnow() - comp_time <= timedelta(hours=24):
                        allowed = True
    if not allowed:
        flash("You are not allowed to add expenses to this trip", "error")
        return redirect(url_for('trip_detail', trip_id=trip_id))

    category = request.form.get("category")
    amount = float(request.form.get("amount") or 0)
    currency = request.form.get("currency", "USD")
    description = request.form.get("description")
    receipt_file = request.files.get("receipt")
    receipt_filename = save_file(receipt_file)

    expense = {"category": category, "amount": amount, "currency": currency, "description": description,
               "receipt": receipt_filename, "created_at": datetime.utcnow()}
    db.add_trip_expense(trip_id, expense)
    flash("Expense added", "success")
    return redirect(url_for('trip_detail', trip_id=trip_id))

@app.route("/trips/<trip_id>/mark-complete", methods=["POST"])
def mark_complete(trip_id):
    # owner marks complete - lock exchange rate at completion
    if session.get('user_role') != 'owner':
        flash("Only owner can mark complete", "error")
        return redirect(url_for('trip_detail', trip_id=trip_id))
    current_rate = db.get_exchange_rate()
    db.update_trip(trip_id, {"status": "completed", "completed_at": datetime.utcnow(), "exchange_rate_at": current_rate})
    flash("Trip marked completed", "success")
    return redirect(url_for('trip_detail', trip_id=trip_id))

@app.route("/driver/trips/<trip_id>/complete", methods=["POST"])
def driver_mark_complete(trip_id):
    if session.get('user_role') != 'driver':
        flash("Unauthorized", "error")
        return redirect(url_for('login'))
    trip = db.get_trip(trip_id)
    if not trip or str(trip.get("driver_id")) != session.get('user_id'):
        flash("Trip not found or not assigned to you", "error")
        return redirect(url_for('driver_dashboard'))
    current_rate = db.get_exchange_rate()
    db.update_trip(trip_id, {"status": "completed", "completed_at": datetime.utcnow(), "exchange_rate_at": current_rate})
    flash("Trip marked completed. You may add expenses for 24 hours.", "info")
    return redirect(url_for('trip_detail', trip_id=trip_id))

# -----------------------
# Driver dashboard
# -----------------------
@app.route("/driver")
def driver_dashboard():
    if session.get('user_role') != 'driver':
        flash("Access denied.", "error")
        return redirect(url_for('login'))
    driver_id = session.get('user_id')
    trips = db.list_trips({"driver_id": ObjectId(driver_id)}) if driver_id else []
    for t in trips:
        t['_id'] = str(t['_id'])
    return render_template("driver_dashboard.html", trips=trips)

# -----------------------
# Uploads
# -----------------------
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# -----------------------
# Development / seed
# -----------------------
@app.route("/_seed")
def seed_data():
    if session.get('user_role') != 'owner':
        return "forbidden", 403
    if db.drivers.count_documents({}) == 0:
        db.create_driver({"name": "John Smith", "email": "john@example.com", "phone": "555-0101", "password_hash": generate_password_hash("password")})
        flash("Seed data created.", "success")
    else:
        flash("Database already contains data.", "info")
    return redirect(url_for('owner_dashboard'))

if __name__ == "__main__":
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))