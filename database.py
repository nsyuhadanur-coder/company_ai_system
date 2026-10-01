import sqlite3
import os
from datetime import datetime, date, timedelta

DB_NAME = "inventory.db"

def get_db_connection():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_NAME)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Products table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        category TEXT DEFAULT 'General',
        unit TEXT DEFAULT 'Unit',
        min_stock INTEGER DEFAULT 5,
        cost_price REAL DEFAULT 0.0,
        selling_price REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # Run migration check if table already exists without cost/selling prices
    cursor.execute("PRAGMA table_info(products)")
    existing_cols = [col[1] for col in cursor.fetchall()]
    if 'cost_price' not in existing_cols:
        cursor.execute("ALTER TABLE products ADD COLUMN cost_price REAL DEFAULT 0.0")
    if 'selling_price' not in existing_cols:
        cursor.execute("ALTER TABLE products ADD COLUMN selling_price REAL DEFAULT 0.0")
    
    # Inventory Batches table (tracks stock with expiration date)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        batch_no TEXT,
        quantity INTEGER NOT NULL DEFAULT 0,
        expiration_date DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    )
    """)
    
    # Transactions table (Stock In / Stock Out)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        batch_id INTEGER,
        type TEXT NOT NULL CHECK(type IN ('IN', 'OUT')),
        quantity INTEGER NOT NULL,
        expiration_date DATE,
        reference TEXT,
        user_id INTEGER,
        user_name TEXT DEFAULT 'System',
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
        FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE SET NULL
    )
    """)

    # Migration check for transactions table
    cursor.execute("PRAGMA table_info(transactions)")
    tx_cols = [col[1] for col in cursor.fetchall()]
    if 'user_name' not in tx_cols:
        cursor.execute("ALTER TABLE transactions ADD COLUMN user_name TEXT DEFAULT 'System'")
    if 'user_id' not in tx_cols:
        cursor.execute("ALTER TABLE transactions ADD COLUMN user_id INTEGER")

    # Users table for Multi-User & Role Based Access Control
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'staff' CHECK(role IN ('admin', 'staff', 'viewer')),
        is_active INTEGER NOT NULL DEFAULT 1,
        approval_status TEXT NOT NULL DEFAULT 'approved' CHECK(approval_status IN ('approved', 'pending', 'rejected')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )
    """)

    # Migration check for users table (approval_status & pending_password_hash)
    cursor.execute("PRAGMA table_info(users)")
    user_cols = [col[1] for col in cursor.fetchall()]
    if 'approval_status' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN approval_status TEXT DEFAULT 'approved'")
    if 'pending_password_hash' not in user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN pending_password_hash TEXT")

    # Seed initial default accounts if table is empty
    cursor.execute("SELECT COUNT(*) as count FROM users")
    if cursor.fetchone()['count'] == 0:
        from werkzeug.security import generate_password_hash
        default_users = [
            ("admin", generate_password_hash("admin123"), "System Administrator", "admin", "approved"),
            ("staff", generate_password_hash("staff123"), "Warehouse Staff", "staff", "approved"),
            ("viewer", generate_password_hash("viewer123"), "Inventory Auditor", "viewer", "approved")
        ]
        cursor.executemany("""
            INSERT INTO users (username, password_hash, full_name, role, approval_status)
            VALUES (?, ?, ?, ?, ?)
        """, default_users)
    
    conn.commit()
    conn.close()

# Product helpers
def get_all_products():
    conn = get_db_connection()
    today = date.today().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            p.*, 
            COALESCE(SUM(b.quantity), 0) AS total_stock,
            ROUND(COALESCE(SUM(b.quantity), 0) * p.cost_price, 2) AS total_cost_value,
            ROUND(COALESCE(SUM(b.quantity), 0) * p.selling_price, 2) AS total_sales_value,
            COUNT(CASE WHEN b.quantity > 0 AND b.expiration_date < ? THEN 1 END) AS expired_batches_count,
            COUNT(CASE WHEN b.quantity > 0 AND b.expiration_date BETWEEN ? AND date(?, '+30 days') THEN 1 END) AS expiring_soon_batches_count,
            MIN(CASE WHEN b.quantity > 0 AND b.expiration_date >= ? THEN b.expiration_date END) AS earliest_valid_expiry
        FROM products p
        LEFT JOIN batches b ON p.id = b.product_id
        GROUP BY p.id
        ORDER BY p.name ASC
    """, (today, today, today, today))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_product_by_barcode(barcode):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE barcode = ?", (barcode.strip(),))
    product = cursor.fetchone()
    if not product:
        conn.close()
        return None
    
    prod_dict = dict(product)
    
    # Get active batches with quantity > 0
    today = date.today().isoformat()
    cursor.execute("""
        SELECT *,
            CASE 
                WHEN expiration_date IS NULL THEN 'NO_EXPIRY'
                WHEN expiration_date < ? THEN 'EXPIRED'
                WHEN expiration_date BETWEEN ? AND date(?, '+30 days') THEN 'EXPIRING_SOON'
                ELSE 'VALID'
            END AS expiry_status
        FROM batches 
        WHERE product_id = ? AND quantity > 0 
        ORDER BY 
            CASE WHEN expiration_date IS NULL THEN 1 ELSE 0 END,
            expiration_date ASC
    """, (today, today, today, prod_dict['id']))
    batches = [dict(b) for b in cursor.fetchall()]
    
    prod_dict['batches'] = batches
    prod_dict['total_stock'] = sum(b['quantity'] for b in batches)
    prod_dict['total_cost_value'] = round(prod_dict['total_stock'] * prod_dict.get('cost_price', 0.0), 2)
    prod_dict['total_sales_value'] = round(prod_dict['total_stock'] * prod_dict.get('selling_price', 0.0), 2)
    
    # Recent transactions
    cursor.execute("""
        SELECT t.*, b.batch_no 
        FROM transactions t
        LEFT JOIN batches b ON t.batch_id = b.id
        WHERE t.product_id = ?
        ORDER BY t.timestamp DESC LIMIT 10
    """, (prod_dict['id'],))
    prod_dict['recent_transactions'] = [dict(t) for t in cursor.fetchall()]
    
    conn.close()
    return prod_dict

def create_or_update_product(barcode, name, category='General', unit='Unit', min_stock=5, cost_price=0.0, selling_price=0.0):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO products (barcode, name, category, unit, min_stock, cost_price, selling_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(barcode) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            unit = excluded.unit,
            min_stock = excluded.min_stock,
            cost_price = excluded.cost_price,
            selling_price = excluded.selling_price
    """, (barcode.strip(), name.strip(), category.strip(), unit.strip(), int(min_stock), float(cost_price or 0.0), float(selling_price or 0.0)))
    conn.commit()
    prod_id = cursor.lastrowid
    if not prod_id:
        cursor.execute("SELECT id FROM products WHERE barcode = ?", (barcode.strip(),))
        prod_id = cursor.fetchone()['id']
    conn.close()
    return prod_id

# Stock In
def stock_in(barcode, name, quantity, expiration_date=None, batch_no=None, reference='Stock Received', category='General', unit='Unit', cost_price=None, selling_price=None, user_id=None, user_name='System'):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check or create product
    cursor.execute("SELECT id FROM products WHERE barcode = ?", (barcode.strip(),))
    row = cursor.fetchone()
    if row:
        product_id = row['id']
        updates = []
        params = []
        if name:
            updates.append("name = ?")
            params.append(name.strip())
        if cost_price is not None and cost_price != "":
            updates.append("cost_price = ?")
            params.append(float(cost_price))
        if selling_price is not None and selling_price != "":
            updates.append("selling_price = ?")
            params.append(float(selling_price))
        if updates:
            params.append(product_id)
            cursor.execute(f"UPDATE products SET {', '.join(updates)} WHERE id = ?", params)
    else:
        cursor.execute("""
            INSERT INTO products (barcode, name, category, unit, cost_price, selling_price) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (barcode.strip(), name.strip() if name else f"Item {barcode}", category, unit, float(cost_price or 0.0), float(selling_price or 0.0)))
        product_id = cursor.lastrowid
        
    quantity = int(quantity)
    if quantity <= 0:
        conn.close()
        raise ValueError("Quantity must be greater than 0.")
        
    exp_date = expiration_date.strip() if expiration_date and expiration_date.strip() else None
    b_no = batch_no.strip() if batch_no and batch_no.strip() else f"B{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Check if exact batch with same expiration date exists
    if exp_date:
        cursor.execute("""
            SELECT id, quantity FROM batches 
            WHERE product_id = ? AND expiration_date = ?
            LIMIT 1
        """, (product_id, exp_date))
    else:
        cursor.execute("""
            SELECT id, quantity FROM batches 
            WHERE product_id = ? AND expiration_date IS NULL
            LIMIT 1
        """, (product_id,))
        
    existing_batch = cursor.fetchone()
    if existing_batch:
        batch_id = existing_batch['id']
        new_batch_qty = existing_batch['quantity'] + quantity
        cursor.execute("UPDATE batches SET quantity = ? WHERE id = ?", (new_batch_qty, batch_id))
    else:
        cursor.execute("""
            INSERT INTO batches (product_id, batch_no, quantity, expiration_date)
            VALUES (?, ?, ?, ?)
        """, (product_id, b_no, quantity, exp_date))
        batch_id = cursor.lastrowid

    # Record Transaction with User Attribution
    cursor.execute("""
        INSERT INTO transactions (product_id, batch_id, type, quantity, expiration_date, reference, user_id, user_name)
        VALUES (?, ?, 'IN', ?, ?, ?, ?, ?)
    """, (product_id, batch_id, quantity, exp_date, reference, user_id, user_name or 'System'))

    conn.commit()
    conn.close()
    return {"success": True, "product_id": product_id, "batch_id": batch_id, "quantity_added": quantity}

# Stock Out with FEFO (First Expired, First Out)
def stock_out(barcode, quantity, batch_id=None, reference='Stock Dispatched', user_id=None, user_name='System'):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name FROM products WHERE barcode = ?", (barcode.strip(),))
    product = cursor.fetchone()
    if not product:
        conn.close()
        raise ValueError(f"Product with barcode '{barcode}' was not found.")
        
    product_id = product['id']
    quantity = int(quantity)
    if quantity <= 0:
        conn.close()
        raise ValueError("Quantity must be greater than 0.")
        
    # Check total available stock
    cursor.execute("SELECT COALESCE(SUM(quantity), 0) as total FROM batches WHERE product_id = ? AND quantity > 0", (product_id,))
    total_avail = cursor.fetchone()['total']
    if total_avail < quantity:
        conn.close()
        raise ValueError(f"Insufficient stock! Current stock: {total_avail}, requested: {quantity}.")

    remaining_to_deduct = quantity
    deductions = []

    if batch_id:
        # User specified a specific batch
        cursor.execute("SELECT id, quantity, expiration_date FROM batches WHERE id = ? AND product_id = ?", (batch_id, product_id))
        b = cursor.fetchone()
        if not b or b['quantity'] < quantity:
            conn.close()
            raise ValueError(f"Selected batch quantity ({b['quantity'] if b else 0}) is insufficient to deduct {quantity}.")
        
        new_qty = b['quantity'] - quantity
        cursor.execute("UPDATE batches SET quantity = ? WHERE id = ?", (new_qty, batch_id))
        cursor.execute("""
            INSERT INTO transactions (product_id, batch_id, type, quantity, expiration_date, reference, user_id, user_name)
            VALUES (?, ?, 'OUT', ?, ?, ?, ?, ?)
        """, (product_id, batch_id, quantity, b['expiration_date'], reference, user_id, user_name or 'System'))
        deductions.append({"batch_id": batch_id, "deducted": quantity, "expiry": b['expiration_date']})
    else:
        # FEFO: First Expired First Out (Sort nulls last)
        cursor.execute("""
            SELECT id, quantity, expiration_date 
            FROM batches 
            WHERE product_id = ? AND quantity > 0
            ORDER BY 
                CASE WHEN expiration_date IS NULL THEN 1 ELSE 0 END,
                expiration_date ASC,
                id ASC
        """, (product_id,))
        batches = cursor.fetchall()
        
        for b in batches:
            if remaining_to_deduct <= 0:
                break
            b_id = b['id']
            b_qty = b['quantity']
            b_exp = b['expiration_date']
            
            if b_qty <= remaining_to_deduct:
                deduct_this = b_qty
                new_qty = 0
            else:
                deduct_this = remaining_to_deduct
                new_qty = b_qty - deduct_this
                
            cursor.execute("UPDATE batches SET quantity = ? WHERE id = ?", (new_qty, b_id))
            cursor.execute("""
                INSERT INTO transactions (product_id, batch_id, type, quantity, expiration_date, reference, user_id, user_name)
                VALUES (?, ?, 'OUT', ?, ?, ?, ?, ?)
            """, (product_id, b_id, deduct_this, b_exp, reference, user_id, user_name or 'System'))
            
            remaining_to_deduct -= deduct_this
            deductions.append({"batch_id": b_id, "deducted": deduct_this, "expiry": b_exp})

    conn.commit()
    conn.close()
    return {"success": True, "product_name": product['name'], "quantity_deducted": quantity, "deductions": deductions}

def get_movement_trend_data(period='7days', start_date=None, end_date=None):
    conn = get_db_connection()
    today = date.today()
    cursor = conn.cursor()

    # Determine date boundaries
    if start_date or end_date:
        try:
            start_d = datetime.strptime(start_date.strip(), "%Y-%m-%d").date() if start_date and start_date.strip() else today
        except Exception:
            start_d = today

        try:
            end_d = datetime.strptime(end_date.strip(), "%Y-%m-%d").date() if end_date and end_date.strip() else today
        except Exception:
            end_d = today

        if start_d > end_d:
            start_d, end_d = end_d, start_d

        active_filter = 'custom'
    else:
        if period in ('today',):
            start_d = today
            end_d = today
            active_filter = 'today'
        elif period in ('yesterday',):
            start_d = today - timedelta(days=1)
            end_d = start_d
            active_filter = 'yesterday'
        elif period in ('30days', 'month'):
            start_d = today - timedelta(days=29)
            end_d = today
            active_filter = '30days'
        elif period in ('this_month',):
            start_d = today.replace(day=1)
            end_d = today
            active_filter = 'this_month'
        elif period in ('year', '12months'):
            start_d = (today.replace(day=1) - timedelta(days=365)).replace(day=1)
            end_d = today
            active_filter = 'year'
        else:  # default '7days' / 'week'
            start_d = today - timedelta(days=6)
            end_d = today
            active_filter = '7days'

    labels = []
    data_in = []
    data_out = []
    delta_days = (end_d - start_d).days

    if active_filter == 'year' and not (start_date or end_date):
        # 12 Months Grouping
        for i in range(11, -1, -1):
            year = today.year
            month = today.month - i
            while month <= 0:
                month += 12
                year -= 1
            m_str = f"{year:04d}-{month:02d}"
            labels.append(date(year, month, 1).strftime("%b %Y"))
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(CASE WHEN type = 'IN' THEN quantity ELSE 0 END), 0) as in_qty,
                    COALESCE(SUM(CASE WHEN type = 'OUT' THEN quantity ELSE 0 END), 0) as out_qty
                FROM transactions
                WHERE strftime('%Y-%m', timestamp) = ?
            """, (m_str,))
            row = cursor.fetchone()
            data_in.append(row['in_qty'])
            data_out.append(row['out_qty'])
        title = "12-Month Stock Movement Trend (IN vs OUT)"
        subtitle = "Monthly volume comparison of incoming stock received vs outgoing dispatches"

    elif delta_days == 0:
        # Single Date Selected (Hourly Timeline Breakdown)
        day_str = start_d.isoformat()
        cursor.execute("""
            SELECT 
                strftime('%H', timestamp) as tx_hour,
                COALESCE(SUM(CASE WHEN type = 'IN' THEN quantity ELSE 0 END), 0) as in_qty,
                COALESCE(SUM(CASE WHEN type = 'OUT' THEN quantity ELSE 0 END), 0) as out_qty
            FROM transactions
            WHERE date(timestamp) = ?
            GROUP BY strftime('%H', timestamp)
        """, (day_str,))
        hourly_map = {r['tx_hour']: (r['in_qty'], r['out_qty']) for r in cursor.fetchall()}

        min_h = 8
        max_h = 20
        if hourly_map:
            int_hours = [int(h) for h in hourly_map.keys()]
            min_h = min(min_h, min(int_hours))
            max_h = max(max_h, max(int_hours))

        for h in range(min_h, max_h + 1):
            h_str = f"{h:02d}"
            labels.append(f"{h_str}:00")
            vals = hourly_map.get(h_str, (0, 0))
            data_in.append(vals[0])
            data_out.append(vals[1])

        if start_d == today:
            title = f"Today's Stock Movement ({start_d.strftime('%d %b %Y')})"
        elif start_d == today - timedelta(days=1):
            title = f"Yesterday's Stock Movement ({start_d.strftime('%d %b %Y')})"
        else:
            title = f"Stock Movement for {start_d.strftime('%d %b %Y')}"
        subtitle = "Hourly breakdown of incoming stock received vs outgoing dispatches"

    elif delta_days > 90:
        # Multi-month date range (> 90 days): group by month
        cursor.execute("""
            SELECT 
                strftime('%Y-%m', timestamp) as tx_month,
                COALESCE(SUM(CASE WHEN type = 'IN' THEN quantity ELSE 0 END), 0) as in_qty,
                COALESCE(SUM(CASE WHEN type = 'OUT' THEN quantity ELSE 0 END), 0) as out_qty
            FROM transactions
            WHERE date(timestamp) BETWEEN ? AND ?
            GROUP BY strftime('%Y-%m', timestamp)
        """, (start_d.isoformat(), end_d.isoformat()))
        month_map = {r['tx_month']: (r['in_qty'], r['out_qty']) for r in cursor.fetchall()}

        curr_y = start_d.year
        curr_m = start_d.month
        end_y = end_d.year
        end_m = end_d.month
        while (curr_y < end_y) or (curr_y == end_y and curr_m <= end_m):
            m_str = f"{curr_y:04d}-{curr_m:02d}"
            labels.append(date(curr_y, curr_m, 1).strftime("%b %Y"))
            vals = month_map.get(m_str, (0, 0))
            data_in.append(vals[0])
            data_out.append(vals[1])
            curr_m += 1
            if curr_m > 12:
                curr_m = 1
                curr_y += 1

        title = f"Stock Movement: {start_d.strftime('%d %b %Y')} to {end_d.strftime('%d %b %Y')}"
        subtitle = "Monthly volume comparison over selected date range"

    else:
        # 1 to 90 days: Daily Breakdown
        cursor.execute("""
            SELECT 
                date(timestamp) as tx_date,
                COALESCE(SUM(CASE WHEN type = 'IN' THEN quantity ELSE 0 END), 0) as in_qty,
                COALESCE(SUM(CASE WHEN type = 'OUT' THEN quantity ELSE 0 END), 0) as out_qty
            FROM transactions
            WHERE date(timestamp) BETWEEN ? AND ?
            GROUP BY date(timestamp)
        """, (start_d.isoformat(), end_d.isoformat()))
        daily_map = {r['tx_date']: (r['in_qty'], r['out_qty']) for r in cursor.fetchall()}

        for i in range(delta_days + 1):
            curr_d = start_d + timedelta(days=i)
            labels.append(curr_d.strftime("%d %b"))
            vals = daily_map.get(curr_d.isoformat(), (0, 0))
            data_in.append(vals[0])
            data_out.append(vals[1])

        if active_filter == '7days':
            title = "7-Day Stock Movement Trend (IN vs OUT)"
            subtitle = "Daily volume comparison of incoming stock received vs outgoing dispatches"
        elif active_filter == '30days':
            title = "30-Day Stock Movement Trend (IN vs OUT)"
            subtitle = "Daily volume comparison of incoming stock received vs outgoing dispatches"
        elif active_filter == 'this_month':
            title = f"Stock Movement: {start_d.strftime('%B %Y')}"
            subtitle = f"Daily movement from 1st {start_d.strftime('%b')} to {end_d.strftime('%d %b %Y')}"
        else:
            title = f"Stock Movement: {start_d.strftime('%d %b %Y')} to {end_d.strftime('%d %b %Y')}"
            subtitle = f"Daily volume comparison ({delta_days + 1} days)"

    conn.close()
    return {
        "period": active_filter,
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "title": title,
        "subtitle": subtitle,
        "labels": labels,
        "data_in": data_in,
        "data_out": data_out,
        "total_in": sum(data_in),
        "total_out": sum(data_out),
        "net_movement": sum(data_in) - sum(data_out)
    }

def get_dashboard_summary():
    conn = get_db_connection()
    today = date.today().isoformat()
    cursor = conn.cursor()
    
    # Total products count
    cursor.execute("SELECT COUNT(*) as count FROM products")
    total_products = cursor.fetchone()['count']
    
    # Total items in stock
    cursor.execute("SELECT COALESCE(SUM(quantity), 0) as total FROM batches WHERE quantity > 0")
    total_stock_units = cursor.fetchone()['total']
    
    # Expired batches count
    cursor.execute("""
        SELECT COUNT(DISTINCT product_id) as count 
        FROM batches 
        WHERE quantity > 0 AND expiration_date < ?
    """, (today,))
    expired_products_count = cursor.fetchone()['count']
    
    # Expiring soon batches count (within 30 days)
    cursor.execute("""
        SELECT COUNT(DISTINCT product_id) as count 
        FROM batches 
        WHERE quantity > 0 AND expiration_date BETWEEN ? AND date(?, '+30 days')
    """, (today, today))
    expiring_soon_count = cursor.fetchone()['count']
    
    # Low stock products count
    cursor.execute("""
        SELECT COUNT(*) as count FROM (
            SELECT p.id
            FROM products p
            LEFT JOIN batches b ON p.id = b.product_id
            GROUP BY p.id
            HAVING COALESCE(SUM(b.quantity), 0) <= p.min_stock
        )
    """)
    low_stock_count = cursor.fetchone()['count']

    # Today's In and Out
    cursor.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN type = 'IN' THEN quantity ELSE 0 END), 0) as in_today,
            COALESCE(SUM(CASE WHEN type = 'OUT' THEN quantity ELSE 0 END), 0) as out_today
        FROM transactions
        WHERE date(timestamp) = ?
    """, (today,))
    today_stats = cursor.fetchone()

    # Financial Valuation Metrics
    cursor.execute("""
        SELECT 
            COALESCE(SUM(b.quantity * p.cost_price), 0) AS total_inventory_cost,
            COALESCE(SUM(b.quantity * p.selling_price), 0) AS total_inventory_sales
        FROM batches b
        JOIN products p ON b.product_id = p.id
        WHERE b.quantity > 0
    """)
    fin = cursor.fetchone()
    total_inventory_cost = round(fin['total_inventory_cost'], 2)
    total_inventory_sales = round(fin['total_inventory_sales'], 2)
    potential_profit = round(total_inventory_sales - total_inventory_cost, 2)
    gross_margin_pct = round((potential_profit / total_inventory_sales * 100), 1) if total_inventory_sales > 0 else 0.0

    # Expired Stock Loss Valuation
    cursor.execute("""
        SELECT COALESCE(SUM(b.quantity * p.cost_price), 0) AS expired_loss
        FROM batches b
        JOIN products p ON b.product_id = p.id
        WHERE b.quantity > 0 AND b.expiration_date < ?
    """, (today,))
    expired_loss_value = round(cursor.fetchone()['expired_loss'], 2)

    # 7-day movement trend for default dashboard render
    trend = get_movement_trend_data('7days')

    # Recent transactions
    cursor.execute("""
        SELECT t.*, p.name as product_name, p.barcode
        FROM transactions t
        JOIN products p ON t.product_id = p.id
        ORDER BY t.timestamp DESC LIMIT 8
    """)
    recent_tx = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {
        "total_products": total_products,
        "total_stock_units": total_stock_units,
        "expired_products_count": expired_products_count,
        "expiring_soon_count": expiring_soon_count,
        "low_stock_count": low_stock_count,
        "in_today": today_stats['in_today'],
        "out_today": today_stats['out_today'],
        "total_inventory_cost": total_inventory_cost,
        "total_inventory_sales": total_inventory_sales,
        "potential_profit": potential_profit,
        "gross_margin_pct": gross_margin_pct,
        "expired_loss_value": expired_loss_value,
        "trend_period": trend["period"],
        "trend_start_date": trend["start_date"],
        "trend_end_date": trend["end_date"],
        "trend_title": trend["title"],
        "trend_subtitle": trend["subtitle"],
        "trend_labels": trend["labels"],
        "trend_in": trend["data_in"],
        "trend_out": trend["data_out"],
        "trend_total_in": trend["total_in"],
        "trend_total_out": trend["total_out"],
        "trend_net_movement": trend["net_movement"],
        "recent_transactions": recent_tx
    }

def get_transactions_log(limit=100, filter_type=None, start_date=None, end_date=None, search_query=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT t.*, p.name as product_name, p.barcode, b.batch_no
        FROM transactions t
        JOIN products p ON t.product_id = p.id
        LEFT JOIN batches b ON t.batch_id = b.id
    """
    conditions = []
    params = []
    
    if filter_type in ('IN', 'OUT'):
        conditions.append("t.type = ?")
        params.append(filter_type)
        
    if start_date:
        conditions.append("date(t.timestamp) >= ?")
        params.append(start_date.strip())
        
    if end_date:
        conditions.append("date(t.timestamp) <= ?")
        params.append(end_date.strip())
        
    if search_query:
        conditions.append("(p.name LIKE ? OR p.barcode LIKE ? OR t.reference LIKE ? OR b.batch_no LIKE ?)")
        term = f"%{search_query.strip()}%"
        params.extend([term, term, term, term])
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY t.timestamp DESC"
    
    if limit is not None and int(limit) > 0:
        query += " LIMIT ?"
        params.append(int(limit))
        
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_expiring_batches():
    conn = get_db_connection()
    today = date.today().isoformat()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.*, p.name as product_name, p.barcode, p.cost_price,
            ROUND(b.quantity * p.cost_price, 2) AS batch_cost_value,
            CASE 
                WHEN b.expiration_date < ? THEN 'EXPIRED'
                ELSE 'EXPIRING_SOON'
            END AS status,
            CAST(julianday(b.expiration_date) - julianday(?) AS INTEGER) as days_remaining
        FROM batches b
        JOIN products p ON b.product_id = p.id
        WHERE b.quantity > 0 AND b.expiration_date <= date(?, '+30 days')
        ORDER BY b.expiration_date ASC
    """, (today, today, today))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_product(product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    return True

# ----------------- USER MANAGEMENT & AUTHENTICATION ----------------- #

def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, full_name, role, is_active, created_at, last_login FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, full_name, role, is_active, approval_status, created_at, last_login 
        FROM users 
        WHERE approval_status != 'pending'
        ORDER BY 
            CASE role WHEN 'admin' THEN 1 WHEN 'staff' THEN 2 ELSE 3 END,
            id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pending_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, full_name, role, is_active, approval_status, created_at 
        FROM users 
        WHERE approval_status = 'pending'
        ORDER BY id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pending_users_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE approval_status = 'pending'")
    count = cursor.fetchone()['count']
    conn.close()
    return count

def register_user(username, password, full_name, role='viewer'):
    from werkzeug.security import generate_password_hash
    username = username.strip().lower()
    full_name = full_name.strip()
    role = role.strip().lower()
    if role not in ('staff', 'viewer'):
        role = 'viewer'
    if not username or not password or not full_name:
        raise ValueError("User ID, password, dan nama penuh diperlukan.")
    if len(username) < 3:
        raise ValueError("User ID mestilah sekurang-kurangnya 3 aksara.")
    if len(password.strip()) < 4:
        raise ValueError("Password mestilah sekurang-kurangnya 4 aksara.")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE LOWER(username) = ?", (username,))
    if cursor.fetchone():
        conn.close()
        raise ValueError(f"User ID '{username}' telah didaftarkan. Sila pilih User ID yang lain.")
        
    pwd_hash = generate_password_hash(password.strip())
    cursor.execute("""
        INSERT INTO users (username, password_hash, full_name, role, is_active, approval_status)
        VALUES (?, ?, ?, ?, 0, 'pending')
    """, (username, pwd_hash, full_name, role))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id

def approve_user(user_id, role=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise ValueError("User tidak dijumpai.")
        
    updates = ["approval_status = 'approved'", "is_active = 1"]
    params = []
    if role and role.strip().lower() in ('admin', 'staff', 'viewer'):
        updates.append("role = ?")
        params.append(role.strip().lower())
    params.append(user_id)
    
    cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return True

def reject_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise ValueError("User tidak dijumpai.")
        
    cursor.execute("DELETE FROM users WHERE id = ? AND approval_status = 'pending'", (user_id,))
    conn.commit()
    conn.close()
    return True

def request_password_reset(user_identifier, new_password):
    from werkzeug.security import generate_password_hash
    ident = str(user_identifier).strip()
    if not ident:
        raise ValueError("Sila masukkan User ID anda.")
    if not new_password or len(str(new_password).strip()) < 4:
        raise ValueError("Kata laluan baharu mestilah sekurang-kurangnya 4 aksara.")
        
    user = get_user_by_identifier(ident)
    if not user:
        raise ValueError(f"User ID '{ident}' tidak dijumpai dalam pangkalan data sistem.")
    if not user['is_active']:
        raise ValueError(f"Akaun '{user['username']}' dinyahaktifkan. Sila hubungi Administrator.")
        
    pwd_hash = generate_password_hash(str(new_password).strip())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET pending_password_hash = ? WHERE id = ?", (pwd_hash, user['id']))
    conn.commit()
    conn.close()
    return user

def get_password_reset_requests():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, full_name, role, created_at 
        FROM users 
        WHERE pending_password_hash IS NOT NULL
        ORDER BY id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_password_reset_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE pending_password_hash IS NOT NULL")
    count = cursor.fetchone()['count']
    conn.close()
    return count

def approve_password_reset(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, pending_password_hash FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise ValueError("User tidak dijumpai.")
    if not target['pending_password_hash']:
        conn.close()
        raise ValueError("Tiada permohonan reset kata laluan aktif bagi pengguna ini.")
        
    cursor.execute("""
        UPDATE users 
        SET password_hash = pending_password_hash, pending_password_hash = NULL 
        WHERE id = ?
    """, (user_id,))
    conn.commit()
    conn.close()
    return True

def reject_password_reset(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET pending_password_hash = NULL WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

def create_user(username, password, full_name, role='staff'):
    from werkzeug.security import generate_password_hash
    username = username.strip().lower()
    full_name = full_name.strip()
    role = role.strip().lower()
    if role not in ('admin', 'staff', 'viewer'):
        role = 'staff'
    if not username or not password or not full_name:
        raise ValueError("Username, password, and full name are required.")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE LOWER(username) = ?", (username,))
    if cursor.fetchone():
        conn.close()
        raise ValueError(f"Username '{username}' is already taken. Please choose another username.")
        
    pwd_hash = generate_password_hash(password.strip())
    cursor.execute("""
        INSERT INTO users (username, password_hash, full_name, role, is_active, approval_status)
        VALUES (?, ?, ?, ?, 1, 'approved')
    """, (username, pwd_hash, full_name, role))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id

def update_user(user_id, full_name=None, role=None, is_active=None, password=None):
    from werkzeug.security import generate_password_hash
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if full_name is not None and full_name.strip():
        updates.append("full_name = ?")
        params.append(full_name.strip())
        
    if role is not None and role.strip().lower() in ('admin', 'staff', 'viewer'):
        # Safety check: Cannot demote the only active admin
        new_role = role.strip().lower()
        if new_role != 'admin':
            cursor.execute("SELECT COUNT(*) as admin_count FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?", (user_id,))
            if cursor.fetchone()['admin_count'] == 0:
                conn.close()
                raise ValueError("Cannot remove admin privileges from the only active administrator.")
        updates.append("role = ?")
        params.append(new_role)
        
    if is_active is not None:
        active_val = 1 if is_active else 0
        if active_val == 0:
            # Safety check: Cannot deactivate the only active admin
            cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
            curr_user = cursor.fetchone()
            if curr_user and curr_user['role'] == 'admin':
                cursor.execute("SELECT COUNT(*) as admin_count FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?", (user_id,))
                if cursor.fetchone()['admin_count'] == 0:
                    conn.close()
                    raise ValueError("Cannot deactivate the only active administrator.")
        updates.append("is_active = ?")
        params.append(active_val)
        
    if password is not None and password.strip():
        updates.append("password_hash = ?")
        params.append(generate_password_hash(password.strip()))
        
    if not updates:
        conn.close()
        return False
        
    params.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()
    return True

def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise ValueError("User was not found.")
        
    if target['role'] == 'admin':
        cursor.execute("SELECT COUNT(*) as admin_count FROM users WHERE role = 'admin' AND is_active = 1 AND id != ?", (user_id,))
        if cursor.fetchone()['admin_count'] == 0:
            conn.close()
            raise ValueError("Cannot delete the only active administrator account.")
            
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True

def get_user_by_identifier(identifier):
    conn = get_db_connection()
    cursor = conn.cursor()
    ident = str(identifier).strip()
    if ident.isdigit():
        cursor.execute("SELECT * FROM users WHERE id = ? OR LOWER(username) = LOWER(?)", (int(ident), ident))
    else:
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (ident,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def verify_user_credentials(user_identifier, password):
    from werkzeug.security import check_password_hash
    if not user_identifier or not str(user_identifier).strip():
        return None, "Sila masukkan User ID anda."
    if not password or not str(password).strip():
        return None, "Sila masukkan Password anda."
        
    user = get_user_by_identifier(user_identifier)
    if not user:
        return None, f"User ID '{user_identifier}' tidak dijumpai dalam sistem."
        
    if not check_password_hash(user['password_hash'], str(password).strip()):
        return None, "Password tidak sah. Sila semak semula kata laluan anda."

    approval_status = user.get('approval_status', 'approved')
    if approval_status == 'pending':
        return None, f"Akaun '{user['username']}' sedang MENUNGGU KELULUSAN daripada Administrator sebelum boleh digunakan."
    if approval_status == 'rejected':
        return None, f"Permohonan pendaftaran akaun '{user['username']}' telah DITOLAK oleh Administrator."
        
    if not user['is_active']:
        return None, f"Akaun User ID '{user['username']}' telah dinyahaktifkan. Sila hubungi Administrator."
        
    # Update last login timestamp
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_login = datetime('now', 'localtime') WHERE id = ?", (user['id'],))
    conn.commit()
    conn.close()
    
    return {
        "id": user['id'],
        "username": user['username'],
        "full_name": user['full_name'],
        "role": user['role']
    }, None

