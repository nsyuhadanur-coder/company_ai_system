import os
import csv
import io
from functools import wraps
from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response, session
import database

app = Flask(__name__)
app.secret_key = "barcode-inventory-secret-key"

# Ensure DB is initialized
database.init_db()

API_SECRET_KEY = "barcode-api-secret-key-2026"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.headers.get("X-API-KEY") == API_SECRET_KEY:
            return f(*args, **kwargs)
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Authentication required. Please log in."}), 401
            return redirect(url_for("login_page", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.headers.get("X-API-KEY") == API_SECRET_KEY:
                return f(*args, **kwargs)
            if "user_id" not in session:
                if request.path.startswith("/api/"):
                    return jsonify({"success": False, "message": "Authentication required. Please log in."}), 401
                return redirect(url_for("login_page", next=request.url))
            user_role = session.get("role", "viewer")
            if user_role not in allowed_roles:
                if request.path.startswith("/api/"):
                    return jsonify({"success": False, "message": f"Access denied. Requires one of roles: {', '.join(allowed_roles)}"}), 403
                flash(f"Access Denied: This action requires '{'/'.join(allowed_roles)}' privileges.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.context_processor
def inject_user_context():
    pending_count = 0
    reset_count = 0
    if "user_id" in session and session.get("role") == "admin":
        try:
            pending_count = database.get_pending_users_count()
            reset_count = database.get_password_reset_count()
        except Exception:
            pass
    return {
        "current_user": {
            "id": session.get("user_id"),
            "username": session.get("username"),
            "full_name": session.get("full_name"),
            "role": session.get("role")
        } if "user_id" in session else None,
        "pending_users_count": pending_count,
        "reset_requests_count": reset_count,
        "total_admin_notices": pending_count + reset_count
    }

def _get_filtered_transactions(args, limit=200):
    filter_type = args.get("type", None)
    if filter_type not in ('IN', 'OUT'):
        filter_type = None
    preset = args.get("preset", "all")
    start_date = args.get("start_date", "").strip() or None
    end_date = args.get("end_date", "").strip() or None
    search_query = args.get("q", "").strip() or None

    today = date.today()
    if preset == 'today':
        start_date = today.isoformat()
        end_date = today.isoformat()
    elif preset == 'yesterday':
        yesterday = today - timedelta(days=1)
        start_date = yesterday.isoformat()
        end_date = yesterday.isoformat()
    elif preset == '7days':
        start_date = (today - timedelta(days=7)).isoformat()
        end_date = today.isoformat()
    elif preset == '30days':
        start_date = (today - timedelta(days=30)).isoformat()
        end_date = today.isoformat()
    elif preset == 'this_month':
        start_date = today.replace(day=1).isoformat()
        end_date = today.isoformat()
    elif preset == 'custom':
        # Keep user provided start_date and end_date
        pass
    else:
        preset = 'all'

    txs = database.get_transactions_log(
        limit=limit,
        filter_type=filter_type,
        start_date=start_date,
        end_date=end_date,
        search_query=search_query
    )
    return txs, filter_type, preset, start_date, end_date, search_query

# ----------------- AUTHENTICATION ROUTES ----------------- #

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
        
    next_url = request.args.get("next") or request.form.get("next") or url_for("dashboard")
    
    if request.method == "POST":
        user_id_input = request.form.get("user_id", "").strip() or request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        if not user_id_input:
            flash("Sila masukkan User ID anda.", "warning")
            return render_template("login.html", next_url=next_url)
            
        if not password:
            flash("Sila masukkan Password anda.", "warning")
            return render_template("login.html", next_url=next_url, user_id=user_id_input)

        user, err = database.verify_user_credentials(user_id_input, password)
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name']}! Logged in as {user['role'].title()}.", "success")
            return redirect(next_url)
        else:
            flash(err or "User ID atau Password tidak sah.", "danger")
            return render_template("login.html", next_url=next_url, user_id=user_id_input)
            
    return render_template("login.html", next_url=next_url)

@app.route("/register", methods=["GET", "POST"])
def register_page():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        role = request.form.get("role", "viewer").strip().lower()
        
        if not username or not full_name or not password:
            flash("Sila lengkapkan semua ruangan bertanda *.", "warning")
            return render_template("register.html", username=username, full_name=full_name, role=role)
            
        if len(username) < 3:
            flash("User ID mestilah sekurang-kurangnya 3 aksara.", "warning")
            return render_template("register.html", username=username, full_name=full_name, role=role)
            
        if password != confirm_password:
            flash("Kata laluan dan pengesahan kata laluan tidak sepadan.", "danger")
            return render_template("register.html", username=username, full_name=full_name, role=role)
            
        if len(password) < 4:
            flash("Kata laluan mestilah sekurang-kurangnya 4 aksara.", "warning")
            return render_template("register.html", username=username, full_name=full_name, role=role)
            
        try:
            database.register_user(username, password, full_name, role)
            flash(f"Permohonan pendaftaran untuk User ID '{username}' telah berjaya dihantar! Akaun anda sedang menunggu kelulusan daripada Administrator sebelum boleh log masuk.", "success")
            return redirect(url_for("login_page", user_id=username))
        except Exception as e:
            flash(str(e), "danger")
            return render_template("register.html", username=username, full_name=full_name, role=role)
            
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been successfully logged out.", "info")
    return redirect(url_for("login_page"))

# ----------------- USER MANAGEMENT (ADMIN ONLY) ----------------- #

@app.route("/users")
@login_required
@role_required(["admin"])
def users_page():
    users = database.get_all_users()
    pending_users = database.get_pending_users()
    reset_requests = database.get_password_reset_requests()
    return render_template("users.html", users=users, pending_users=pending_users, reset_requests=reset_requests)

@app.route("/api/forgot-password", methods=["POST"])
def api_forgot_password():
    data = request.get_json() or request.form
    user_id = data.get("user_id", "").strip()
    new_password = data.get("new_password", "").strip()
    confirm_password = data.get("confirm_password", "").strip()
    
    if not user_id:
        return jsonify({"success": False, "message": "Sila masukkan User ID anda."}), 400
    if not new_password:
        return jsonify({"success": False, "message": "Sila masukkan kata laluan baharu."}), 400
    if len(new_password) < 4:
        return jsonify({"success": False, "message": "Kata laluan baharu mestilah sekurang-kurangnya 4 aksara."}), 400
    if new_password != confirm_password:
        return jsonify({"success": False, "message": "Kata laluan dan pengesahan kata laluan tidak sepadan."}), 400
        
    try:
        database.request_password_reset(user_id, new_password)
        return jsonify({
            "success": True, 
            "message": f"Permohonan reset kata laluan bagi User ID '{user_id}' telah berjaya dihantar kepada Administrator untuk kelulusan."
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/users/approve-password-reset/<int:user_id>", methods=["POST"])
@login_required
@role_required(["admin"])
def api_approve_password_reset(user_id):
    try:
        database.approve_password_reset(user_id)
        return jsonify({"success": True, "message": "Kata laluan baharu pengguna telah berjaya diluluskan dan diaktifkan."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/users/reject-password-reset/<int:user_id>", methods=["POST"])
@login_required
@role_required(["admin"])
def api_reject_password_reset(user_id):
    try:
        database.reject_password_reset(user_id)
        return jsonify({"success": True, "message": "Permohonan reset kata laluan telah dibatalkan."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/users/add", methods=["POST"])
@login_required
@role_required(["admin"])
def api_add_user():
    data = request.get_json() or request.form
    username = data.get("username", "").strip()
    full_name = data.get("full_name", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "staff").strip().lower()
    
    try:
        user_id = database.create_user(username, password, full_name, role)
        return jsonify({"success": True, "message": f"User '{username}' created successfully.", "user_id": user_id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/users/update/<int:user_id>", methods=["POST"])
@login_required
@role_required(["admin"])
def api_update_user(user_id):
    data = request.get_json() or request.form
    full_name = data.get("full_name")
    role = data.get("role")
    is_active = data.get("is_active")
    if is_active is not None:
        is_active = True if str(is_active).lower() in ('true', '1') else False
    password = data.get("password")
    if password and not str(password).strip():
        password = None
        
    try:
        database.update_user(user_id, full_name=full_name, role=role, is_active=is_active, password=password)
        if session.get("user_id") == user_id:
            if full_name: session["full_name"] = full_name
            if role: session["role"] = role
        return jsonify({"success": True, "message": "User details updated successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/users/delete/<int:user_id>", methods=["POST", "DELETE"])
@login_required
@role_required(["admin"])
def api_delete_user(user_id):
    if session.get("user_id") == user_id:
        return jsonify({"success": False, "message": "You cannot delete your own active administrator account."}), 400
    try:
        database.delete_user(user_id)
        return jsonify({"success": True, "message": "User deleted successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/users/approve/<int:user_id>", methods=["POST"])
@login_required
@role_required(["admin"])
def api_approve_user(user_id):
    data = request.get_json() or request.form or {}
    role = data.get("role")
    try:
        database.approve_user(user_id, role=role)
        return jsonify({"success": True, "message": "Permohonan pendaftaran pengguna berjaya diluluskan."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/users/reject/<int:user_id>", methods=["POST", "DELETE"])
@login_required
@role_required(["admin"])
def api_reject_user(user_id):
    try:
        database.reject_user(user_id)
        return jsonify({"success": True, "message": "Permohonan pendaftaran pengguna telah ditolak."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

# ----------------- WEB ROUTES ----------------- #

@app.route("/")
@login_required
def dashboard():
    summary = database.get_dashboard_summary()
    if session.get("role") == "viewer":
        summary["total_inventory_cost"] = 0.0
        summary["total_inventory_sales"] = 0.0
        summary["potential_profit"] = 0.0
        summary["gross_margin_pct"] = 0.0
        summary["expired_loss_value"] = 0.0
    expiring_items = database.get_expiring_batches()
    return render_template("dashboard.html", summary=summary, expiring_items=expiring_items)

@app.route("/scan")
@login_required
def scan_page():
    mode = request.args.get("mode", "check") # 'check', 'in', 'out'
    if session.get("role") == "viewer" and mode in ("in", "out"):
        flash("Auditors/Viewers have read-only access. Switched to Check Mode.", "warning")
        mode = "check"
    return render_template("scan.html", active_mode=mode)

@app.route("/products")
@login_required
def products_page():
    products = database.get_all_products()
    if session.get("role") == "viewer":
        for p in products:
            p["cost_price"] = 0.0
            p["selling_price"] = 0.0
            p["total_cost_value"] = 0.0
            p["total_sales_value"] = 0.0
    return render_template("products.html", products=products)

@app.route("/expiring")
@login_required
def expiring_page():
    expiring_items = database.get_expiring_batches()
    if session.get("role") == "viewer":
        for item in expiring_items:
            item["cost_price"] = 0.0
            item["batch_cost_value"] = 0.0
    return render_template("expiring.html", items=expiring_items)

@app.route("/transactions")
@login_required
def transactions_page():
    txs, filter_type, preset, start_date, end_date, search_query = _get_filtered_transactions(request.args, limit=200)
    
    total_count = len(txs)
    total_in = sum(t['quantity'] for t in txs if t['type'] == 'IN')
    total_out = sum(t['quantity'] for t in txs if t['type'] == 'OUT')
    net_movement = total_in - total_out
    
    stats = {
        "total_count": total_count,
        "total_in": total_in,
        "total_out": total_out,
        "net_movement": net_movement
    }
    
    return render_template(
        "transactions.html", 
        transactions=txs, 
        current_filter=filter_type,
        preset=preset,
        start_date=start_date or "",
        end_date=end_date or "",
        search_query=search_query or "",
        stats=stats
    )

@app.route("/barcode-generator")
@login_required
def barcode_generator_page():
    products = database.get_all_products()
    return render_template("barcode_generator.html", products=products)

# ----------------- EXPORT REPORTS (EXCEL / CSV) ----------------- #

@app.route("/export/transactions")
@login_required
def export_transactions():
    txs, filter_type, preset, start_date, end_date, search_query = _get_filtered_transactions(request.args, limit=None)
    
    output = io.StringIO()
    output.write('\ufeff') # UTF-8 BOM for Microsoft Excel
    writer = csv.writer(output)
    
    writer.writerow([
        "Transaction ID",
        "Timestamp",
        "Type",
        "Barcode",
        "Product Name",
        "Batch No",
        "Quantity",
        "Expiration Date",
        "Reference / Notes",
        "Handled By"
    ])
    
    for t in txs:
        writer.writerow([
            t['id'],
            t['timestamp'],
            t['type'],
            f"'{t['barcode']}",
            t['product_name'],
            t['batch_no'] or 'N/A',
            t['quantity'],
            t['expiration_date'] or 'N/A',
            t['reference'] or '',
            t.get('user_name') or 'System'
        ])
        
    filename = f"transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/export/inventory")
@login_required
def export_inventory():
    products = database.get_all_products()
    is_viewer = session.get("role") == "viewer"
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    
    if is_viewer:
        writer.writerow([
            "Barcode",
            "Product Name",
            "Category",
            "Current Stock",
            "Unit",
            "Min Threshold",
            "Stock Status",
            "Earliest Expiry Date",
            "Expired Batches Count",
            "Expiring Soon Batches Count"
        ])
        for p in products:
            if p['total_stock'] <= 0:
                status = "Out of Stock"
            elif p['total_stock'] <= p['min_stock']:
                status = "Low Stock"
            else:
                status = "In Stock"
                
            writer.writerow([
                f"'{p['barcode']}",
                p['name'],
                p['category'] or 'General',
                p['total_stock'],
                p['unit'] or 'Unit',
                p['min_stock'],
                status,
                p['earliest_valid_expiry'] or 'No Expiry',
                p['expired_batches_count'],
                p['expiring_soon_batches_count']
            ])
    else:
        writer.writerow([
            "Barcode",
            "Product Name",
            "Category",
            "Current Stock",
            "Unit",
            "Cost Price (RM)",
            "Selling Price (RM)",
            "Total Cost Value (RM)",
            "Total Sales Value (RM)",
            "Min Threshold",
            "Stock Status",
            "Earliest Expiry Date",
            "Expired Batches Count",
            "Expiring Soon Batches Count"
        ])
        for p in products:
            if p['total_stock'] <= 0:
                status = "Out of Stock"
            elif p['total_stock'] <= p['min_stock']:
                status = "Low Stock"
            else:
                status = "In Stock"
                
            writer.writerow([
                f"'{p['barcode']}",
                p['name'],
                p['category'] or 'General',
                p['total_stock'],
                p['unit'] or 'Unit',
                f"{p.get('cost_price', 0.0):.2f}",
                f"{p.get('selling_price', 0.0):.2f}",
                f"{p.get('total_cost_value', 0.0):.2f}",
                f"{p.get('total_sales_value', 0.0):.2f}",
                p['min_stock'],
                status,
                p['earliest_valid_expiry'] or 'No Expiry',
                p['expired_batches_count'],
                p['expiring_soon_batches_count']
            ])
        
    filename = f"inventory_stock_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/export/expiring")
@login_required
def export_expiring():
    items = database.get_expiring_batches()
    is_viewer = session.get("role") == "viewer"
    
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    
    if is_viewer:
        writer.writerow([
            "Barcode",
            "Product Name",
            "Batch No",
            "Quantity",
            "Expiration Date",
            "Status",
            "Days Remaining"
        ])
        for item in items:
            status_text = "Expired" if item['status'] == 'EXPIRED' else "Expiring Soon"
            writer.writerow([
                f"'{item['barcode']}",
                item['product_name'],
                item['batch_no'] or 'N/A',
                item['quantity'],
                item['expiration_date'],
                status_text,
                item['days_remaining']
            ])
    else:
        writer.writerow([
            "Barcode",
            "Product Name",
            "Batch No",
            "Quantity",
            "Unit Cost (RM)",
            "Estimated Loss Value (RM)",
            "Expiration Date",
            "Status",
            "Days Remaining"
        ])
        for item in items:
            status_text = "Expired" if item['status'] == 'EXPIRED' else "Expiring Soon"
            writer.writerow([
                f"'{item['barcode']}",
                item['product_name'],
                item['batch_no'] or 'N/A',
                item['quantity'],
                f"{item.get('cost_price', 0.0):.2f}",
                f"{item.get('batch_cost_value', 0.0):.2f}",
                item['expiration_date'],
                status_text,
                item['days_remaining']
            ])
        
    filename = f"expiring_batches_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ----------------- REST API (FOR SYSTEM & OFFICE INTEGRATION) ----------------- #

@app.route("/api/product/<barcode>", methods=["GET"])
@login_required
def api_get_product(barcode):
    prod = database.get_product_by_barcode(barcode)
    if prod:
        if session.get("role") == "viewer":
            prod["cost_price"] = 0.0
            prod["selling_price"] = 0.0
            prod["total_cost_value"] = 0.0
            prod["total_sales_value"] = 0.0
        return jsonify({"success": True, "product": prod})
    return jsonify({"success": False, "message": "Product not found"}), 404

@app.route("/api/stock-in", methods=["POST"])
@login_required
@role_required(["admin", "staff"])
def api_stock_in():
    data = request.get_json() or request.form
    barcode = data.get("barcode", "").strip()
    name = data.get("name", "").strip()
    quantity = data.get("quantity")
    expiration_date = data.get("expiration_date", "").strip() or None
    category = data.get("category", "General").strip()
    unit = data.get("unit", "Unit").strip()
    reference = data.get("reference", "Stock Received").strip()
    cost_price = data.get("cost_price", None)
    selling_price = data.get("selling_price", None)
    
    if not barcode:
        return jsonify({"success": False, "message": "Barcode is required"}), 400
    try:
        qty = int(quantity)
        if qty <= 0:
            return jsonify({"success": False, "message": "Quantity must be greater than 0"}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid quantity"}), 400

    u_id = session.get("user_id")
    u_name = session.get("username") or "System"

    try:
        res = database.stock_in(
            barcode=barcode,
            name=name,
            quantity=qty,
            expiration_date=expiration_date,
            reference=reference,
            category=category,
            unit=unit,
            cost_price=cost_price,
            selling_price=selling_price,
            user_id=u_id,
            user_name=u_name
        )
        updated_prod = database.get_product_by_barcode(barcode)
        return jsonify({
            "success": True, 
            "message": f"Successfully received {qty} unit(s) for {updated_prod['name']}",
            "product": updated_prod
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/stock-out", methods=["POST"])
@login_required
@role_required(["admin", "staff"])
def api_stock_out():
    data = request.get_json() or request.form
    barcode = data.get("barcode", "").strip()
    quantity = data.get("quantity")
    batch_id = data.get("batch_id")
    reference = data.get("reference", "Stock Dispatched").strip()
    
    if not barcode:
        return jsonify({"success": False, "message": "Barcode is required"}), 400
    try:
        qty = int(quantity)
        if qty <= 0:
            return jsonify({"success": False, "message": "Quantity must be greater than 0"}), 400
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Invalid quantity"}), 400

    batch_id_val = int(batch_id) if batch_id and str(batch_id).isdigit() else None
    u_id = session.get("user_id")
    u_name = session.get("username") or "System"

    try:
        res = database.stock_out(
            barcode=barcode,
            quantity=qty,
            batch_id=batch_id_val,
            reference=reference,
            user_id=u_id,
            user_name=u_name
        )
        updated_prod = database.get_product_by_barcode(barcode)
        return jsonify({
            "success": True, 
            "message": f"Successfully dispatched {qty} unit(s) of {res['product_name']}",
            "result": res,
            "product": updated_prod
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/products", methods=["GET"])
@login_required
def api_list_products():
    products = database.get_all_products()
    if session.get("role") == "viewer":
        for prod in products:
            prod["cost_price"] = 0.0
            prod["selling_price"] = 0.0
            prod["total_cost_value"] = 0.0
            prod["total_sales_value"] = 0.0
    return jsonify({"success": True, "count": len(products), "products": products})

@app.route("/api/product/save", methods=["POST"])
@login_required
@role_required(["admin", "staff"])
def api_save_product():
    data = request.get_json() or request.form
    barcode = data.get("barcode", "").strip()
    name = data.get("name", "").strip()
    category = data.get("category", "General").strip()
    unit = data.get("unit", "Unit").strip()
    min_stock = data.get("min_stock", 5)
    cost_price = data.get("cost_price", 0.0)
    selling_price = data.get("selling_price", 0.0)

    if not barcode or not name:
        return jsonify({"success": False, "message": "Barcode and Product Name are required"}), 400

    try:
        min_s = int(min_stock)
    except ValueError:
        min_s = 5

    try:
        c_price = float(cost_price or 0.0)
        s_price = float(selling_price or 0.0)
    except ValueError:
        c_price = 0.0
        s_price = 0.0

    try:
        prod_id = database.create_or_update_product(barcode, name, category, unit, min_s, c_price, s_price)
        return jsonify({"success": True, "message": "Product details saved successfully", "product_id": prod_id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/product/delete/<int:product_id>", methods=["POST", "DELETE"])
@login_required
@role_required(["admin"])
def api_delete_product(product_id):
    try:
        database.delete_product(product_id)
        return jsonify({"success": True, "message": "Product deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/dashboard-stats", methods=["GET"])
@login_required
def api_dashboard_stats():
    summary = database.get_dashboard_summary()
    if session.get("role") == "viewer":
        summary["total_inventory_cost"] = 0.0
        summary["total_inventory_sales"] = 0.0
        summary["potential_profit"] = 0.0
        summary["gross_margin_pct"] = 0.0
        summary["expired_loss_value"] = 0.0
    return jsonify({"success": True, "data": summary})

@app.route("/api/analytics/movement-trend", methods=["GET"])
@login_required
def api_movement_trend():
    period = request.args.get("period", "").strip().lower()
    start_date = request.args.get("start_date", "").strip() or None
    end_date = request.args.get("end_date", "").strip() or None
    data = database.get_movement_trend_data(period=period or '7days', start_date=start_date, end_date=end_date)
    return jsonify({"success": True, "data": data})




if __name__ == "__main__":
    print("Starting NexusScan - Barcode & Inventory System...")
    print("Open web browser at: http://127.0.0.1:5000 (or your Raspberry Pi IP address)")
    app.run(host="0.0.0.0", port=5000, debug=True)