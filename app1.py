from flask import Flask, request, jsonify, render_template, redirect, url_for, session,make_response
from flask_cors import CORS
import mysql.connector
import os
import random
import string
from datetime import datetime
import pdfkit

app = Flask(__name__) 

CORS(app)
app.secret_key = 'supersecretkey'  # required for session

# DB Connection
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="CourierDB"
    )

# ====== HTML Page Routes ======
@app.route('/')
def start_page():
    return render_template('signup.html')

@app.route('/login.html')
def login_html():
    return render_template('login.html')

@app.route('/signup.html')
def signup_html():
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard_page():
    if 'user_id' not in session:
        return redirect('/login')

    role = session.get('role', 'customer')
    username = session.get('username', 'User') 
    return render_template('dashboard.html', role=role, username=username)


@app.route('/billing')
def billing_page():
    return render_template('billing.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return '', 204

@app.route('/users.html')
def users_page():
    if 'user_id' not in session or session.get('role') not in ['admin', 'manager']:
        return redirect('/login')
    return render_template('users.html')

# ====== AUTH ======
@app.route("/signup", methods=["POST"])
def signup():
    data = request.json

    if not data.get("username") or not data["username"].strip():
        return jsonify({"success": False, "message": "Username cannot be empty"}), 400
    if not data.get("password"):
        return jsonify({"success": False, "message": "Password cannot be empty"}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        # Check if username already exists
        cur.execute("SELECT user_id FROM Users WHERE username = %s", (data["username"],))
        if cur.fetchone():
            return jsonify({"success": False, "message": "Username already taken"}), 400

        # Check if password already exists (not recommended for security, but you requested it)
        cur.execute("SELECT user_id FROM Users WHERE password = %s", (data["password"],))
        if cur.fetchone():
            return jsonify({"success": False, "message": "Password already in use"}), 400

        cur.execute("INSERT INTO Users (username, password, role) VALUES (%s, %s, %s)",
                    (data["username"].strip(), data["password"], data["role"]))
        user_id = cur.lastrowid

        # Create empty customer if role is customer
        if data["role"] == "customer":
            cur.execute("""
                INSERT INTO Customers (user_id, first_name, last_name, phone, email, address)
                VALUES (%s, '', '', '', '', '')
            """, (user_id,))

        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() 
        username = data.get('username')
        password = data.get('password')

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT user_id, password, role, username FROM Users WHERE username = %s", (username,))
        user = cursor.fetchone()
        
        if user and user[1] == password:
            session['user_id'] = user[0]
            session['role'] = user[2]
            session['username'] = user[3]  # Store username in session
            return jsonify({
                "success": True, 
                "user": {
                    "role": user[2],
                    "username": user[3]
                }
            })
        else:
            return jsonify({"success": False, "message": "Invalid login"})
    return render_template("login.html")

@app.route('/admin/users')
def admin_users():
    if 'user_id' not in session or session.get('role') not in ['admin', 'manager']:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT 
                u.user_id, 
                u.username, 
                u.role,
                c.first_name,
                c.last_name,
                c.email,
                c.phone
            FROM Users u
            LEFT JOIN Customers c ON u.user_id = c.user_id
            ORDER BY u.role DESC, u.user_id
        """)
        users = cur.fetchall()
        return jsonify(users)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/admin/create-manager', methods=['POST'])
def create_manager():
    if 'user_id' not in session or session.get('role') != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required"}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT user_id FROM Users WHERE username = %s", (username,))
        if cur.fetchone():
            return jsonify({"success": False, "message": "Username already exists"}), 400

        cur.execute("INSERT INTO Users (username, password, role) VALUES (%s, %s, 'manager')",
                    (username, password))
        conn.commit()
        return jsonify({"success": True, "message": "Manager account created"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cur.close()
        conn.close()


# ========== CUSTOMER ==========
@app.route("/add-customer", methods=["POST"])
def add_customer():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.callproc("AddCustomer", (data["name"], data["phone"], data["email"], data["address"]))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})

@app.route('/my-orders')
def my_orders():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Unauthorized access"})

    customer_id = get_customer_id(session['user_id'])
    if not customer_id:
        return jsonify({"success": False, "message": "Customer not found"})

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            P.tracking_number, 
            P.type, 
            P.weight, 
            P.priority, 
            P.status,
            (pr.base_fee + (P.weight * pr.rate_per_kg)) AS amount,
            CONCAT(R.first_name, ' ', R.last_name) AS recipient_name,
            R.address AS recipient_address
        FROM Couriers C
        JOIN Packages P ON C.package_id = P.package_id
        JOIN Recipients R ON C.recipient_id = R.recipient_id
        JOIN Pricing pr ON P.priority = pr.priority
        WHERE C.customer_id = %s
    """, (customer_id,))
    
    orders = cursor.fetchall()
    cursor.close()
    db.close()

    return jsonify(orders)

@app.route('/cancel-order/<tracking_number>', methods=['DELETE'])
def cancel_order(tracking_number):
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()
    try:
        # Verify the order belongs to the current user
        cur.execute("""
            SELECT C.courier_id 
            FROM Couriers C
            JOIN Packages P ON C.package_id = P.package_id
            JOIN Customers Cu ON C.customer_id = Cu.customer_id
            WHERE P.tracking_number = %s AND Cu.user_id = %s
        """, (tracking_number, session['user_id']))
        result = cur.fetchone()
        
        if not result:
            return jsonify({"success": False, "message": "Order not found or unauthorized"}), 404

        # Only allow cancellation if status is Pending
        cur.execute("""
    DELETE FROM Couriers 
    WHERE courier_id = %s AND status = 'Pending'
""", (result[0],))
        
        if cur.rowcount == 0:
            return jsonify({"success": False, "message": "Order cannot be cancelled (already processed)"}), 400

        conn.commit()
        return jsonify({"success": True, "message": "Order cancelled"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()


def get_customer_id(user_id):
    con = get_db()
    cursor = con.cursor()
    cursor.execute("SELECT customer_id FROM Customers WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else None

@app.route("/orders")
def orders_page():
    if "user_id" not in session or session.get("role") != "customer":
        return redirect("/login")
    return render_template("orders.html")



# ========== RECIPIENT ==========
@app.route("/add-recipient", methods=["POST"])
def add_recipient():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.callproc("AddRecipient", (data["name"], data["phone"], data["address"]))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})



# ========== COURIER ==========
@app.route("/create-courier", methods=["POST"])
def create_courier():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Unauthorized"})

    data = request.get_json()

    def is_valid_phone(phone):
        return phone.isdigit() and len(phone) == 10
    
    if not is_valid_phone(data["customer"].get("phone", "")):
        return jsonify({"success": False, "message": "Customer phone must be 10 digits"}), 400
    
    if not is_valid_phone(data["recipient"].get("phone", "")):
        return jsonify({"success": False, "message": "Recipient phone must be 10 digits"}), 400
    
    
    
    # Validate required fields
    required_fields = [
        ('customer', ['first_name', 'last_name', 'phone', 'email', 'address']),
        ('recipient', ['first_name', 'last_name', 'phone', 'email', 'address']),
        ('package', ['weight', 'type', 'priority', 'status'])
    ]
    
    for parent, fields in required_fields:
        for field in fields:
            if not data.get(parent, {}).get(field):
                return jsonify({"success": False, "message": f"Missing required field: {parent}.{field}"}), 400
            
    
    # Validate weight is positive number
    try:
        weight = float(data["package"]["weight"])
        if weight <= 0:
            return jsonify({"success": False, "message": "Weight must be positive"}), 400
    except ValueError:
        return jsonify({"success": False, "message": "Invalid weight value"}), 400
    
    # Validate priority is valid
    if data["package"]["priority"] not in ["Low", "Medium", "High"]:
        return jsonify({"success": False, "message": "Invalid priority level"}), 400
    
    # Validate email formats
    import re
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, data["customer"]["email"]):
        return jsonify({"success": False, "message": "Invalid customer email format"}), 400
    if not re.match(email_regex, data["recipient"]["email"]):
        return jsonify({"success": False, "message": "Invalid recipient email format"}), 400
    
    # Rest of your existing courier creation code...
    db = get_db()
    cursor = db.cursor()
    try:
        # ... (keep your existing code)
        # Get current customer_id using logged-in user_id
        cursor.execute("SELECT customer_id FROM Customers WHERE user_id = %s", (session['user_id'],))
        customer = cursor.fetchone()
        
        if not customer:
            return jsonify({"success": False, "message": "Customer not found"})
            
        customer_id = customer[0]

        # Update customer info
        cursor.execute("""
            UPDATE Customers SET 
                first_name = %s,
                last_name = %s,
                phone = %s,
                email = %s,
                address = %s
            WHERE customer_id = %s
        """, (
            data["customer"]["first_name"],
            data["customer"]["last_name"],
            data["customer"]["phone"],
            data["customer"]["email"],
            data["customer"]["address"],
            customer_id
        ))

        # Create recipient
        cursor.execute("""
            INSERT INTO Recipients (first_name, last_name, phone, email, address)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            data["recipient"]["first_name"],
            data["recipient"]["last_name"],
            data["recipient"]["phone"],
            data["recipient"]["email"],
            data["recipient"]["address"]
        ))
        recipient_id = cursor.lastrowid

        # Create package (without customer_id or recipient_id)
        cursor.execute("""
            INSERT INTO Packages (weight, type, priority, status, tracking_number)
            VALUES (%s, %s, %s, %s, CONCAT('TRK', FLOOR(RAND() * 100000000)))
        """, (
            data["package"]["weight"],
            data["package"]["type"],
            data["package"]["priority"],
            data["package"]["status"]
        ))
        package_id = cursor.lastrowid

        # Create courier (linking all entities)
        cursor.execute("""
            INSERT INTO Couriers (customer_id, recipient_id, package_id, status)
            VALUES (%s, %s, %s, %s)
        """, (customer_id, recipient_id, package_id, 'Pending'))

        db.commit()

        # Get the tracking number to return
        cursor.execute("SELECT tracking_number FROM Packages WHERE package_id = %s", (package_id,))
        tracking = cursor.fetchone()[0]

        return jsonify({"success": True, "tracking_number": tracking})

    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cursor.close()
        db.close()
@app.route('/update-order', methods=['POST'])
def update_order():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    data = request.json
    conn = get_db()
    cur = conn.cursor()

    try:
        # Update package details
        cur.execute("""
            UPDATE Packages P
            JOIN Couriers C ON C.package_id = P.package_id
            SET 
                P.type = %s,
                P.weight = %s,
                P.priority = %s
            WHERE P.tracking_number = %s
            AND C.customer_id = (SELECT customer_id FROM Customers WHERE user_id = %s)
        """, (
            data['type'],
            data['weight'],
            data['priority'],
            data['tracking_number'],
            session['user_id']
        ))

        # Update recipient details
        cur.execute("""
            UPDATE Recipients R
            JOIN Couriers C ON C.recipient_id = R.recipient_id
            JOIN Packages P ON C.package_id = P.package_id
            SET 
                R.first_name = %s,
                R.last_name = %s,
                R.address = %s
            WHERE P.tracking_number = %s
            AND C.customer_id = (SELECT customer_id FROM Customers WHERE user_id = %s)
        """, (
            data['recipient_name'].split(' ')[0],  # Assuming first name is first part
            ' '.join(data['recipient_name'].split(' ')[1:]),  # Rest is last name
            data['recipient_address'],
            data['tracking_number'],
            session['user_id']
        ))

        conn.commit()
        return jsonify({"success": True, "message": "Order updated successfully"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route("/track/<tracking_number>")
def track_by_number(tracking_number):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT C.courier_id, P.tracking_number, P.type, P.priority, C.status, C.created_at
        FROM Couriers C
        JOIN Packages P ON C.package_id = P.package_id
        WHERE P.tracking_number = %s
    """, (tracking_number,))
    courier = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({"success": bool(courier), "courier": courier})

@app.route("/couriers", methods=["GET"])
def get_all_couriers():
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.callproc("GetAllCouriers")
        couriers = []
        for r in cur.stored_results():
            couriers = r.fetchall()
        
        # Transform data to match frontend expectations
        formatted_couriers = []
        for courier in couriers:
            formatted = {
                "courier_id": courier["courier_id"],
                "status": courier["status"],
                "created_at": courier["created_at"],
                "tracking_number": courier["tracking_number"],
                "type": courier["type"],
                "priority": courier["priority"],
                "weight": courier["weight"],
                "amount": float(courier["amount"]),
                "customer_name": courier["customer_name"],
                "customer_email": courier["customer_email"],
                "customer_address": courier["customer_address"],
                "recipient_address": courier["recipient_address"]
            }
            formatted_couriers.append(formatted)
        
        return jsonify(formatted_couriers)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        cur.close()
        conn.close()

@app.route('/update-status/<int:cid>', methods=['PUT'])
def update_status(cid):
    if 'user_id' not in session or session.get('role') not in ['admin', 'manager']:
        return jsonify({"message": "Unauthorized"}), 403

    data = request.get_json()
    new_status = data.get('status')

    db = get_db()
    cursor = db.cursor()
    try:
        cursor.callproc('UpdateCourierStatus', [cid, new_status])
        db.commit()
        return jsonify({"message": "Status updated successfully"})
    except Exception as e:
        return jsonify({"message": f"Error: {str(e)}"}), 500
    finally:
        cursor.close()
        db.close()

# ========== PAYMENT ==========
@app.route("/make-payment/<tracking_number>", methods=["POST"])
def make_payment_for_tracking(tracking_number):
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    try:
        # Get package details with calculated price
        cur.execute("""
            SELECT P.*, (pr.base_fee + (P.weight * pr.rate_per_kg)) AS amount,
                   C.courier_id, C.customer_id
            FROM Packages P
            JOIN Couriers C ON C.package_id = P.package_id
            JOIN Pricing pr ON P.priority = pr.priority
            WHERE P.tracking_number = %s
        """, (tracking_number,))
        result = cur.fetchone()

        if not result:
            return jsonify({"success": False, "message": "Tracking number not found"})

        # Insert Payment
        cur.execute("""
            INSERT INTO Payments (courier_id, amount, method)
            VALUES (%s, %s, %s)
        """, (result["courier_id"], result["amount"], "Online"))

        # Update Billing
        cur.execute("""
            INSERT INTO Billing (customer_id, total_amount, billing_date)
            VALUES (%s, %s, CURDATE())
            ON DUPLICATE KEY UPDATE total_amount = total_amount + VALUES(total_amount)
        """, (result["customer_id"], result["amount"]))

        conn.commit()

        return jsonify({
            "success": True,
            "message": f"Payment of ₹{result['amount']:.2f} successful.",
            "amount": result["amount"]
        })

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        cur.close()
        conn.close()

@app.route("/get-my-id")
def get_my_id():
    if 'user_id' not in session:
        return jsonify({"customer_id": None})
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT customer_id FROM Customers WHERE user_id = %s", (session['user_id'],))
        result = cur.fetchone()
        return jsonify({"customer_id": result[0] if result else None})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ========== BILLING ==========
@app.route('/generate-bill')
def generate_bill():
    if 'user_id' not in session:
        return "Login required", 401

    customer_id = get_customer_id(session['user_id'])
    if not customer_id:
        return "Customer not found", 404

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    
    try:
        # Get customer details
        cur.execute("SELECT * FROM Customers WHERE customer_id = %s", (customer_id,))
        customer = cur.fetchone()
        
        # Get all couriers for this customer
        cur.execute("""
            SELECT 
                P.tracking_number, 
                P.type, 
                P.weight, 
                P.priority, 
                P.status,
                (pr.base_fee + (P.weight * pr.rate_per_kg)) AS amount,
                CONCAT(R.first_name, ' ', R.last_name) AS recipient_name,
                R.address AS recipient_address
            FROM Couriers C
            JOIN Packages P ON C.package_id = P.package_id
            JOIN Recipients R ON C.recipient_id = R.recipient_id
            JOIN Pricing pr ON P.priority = pr.priority
            WHERE C.customer_id = %s
        """, (customer_id,))
        couriers = cur.fetchall()
        
        # Calculate total
        total_due = sum(courier['amount'] for courier in couriers) if couriers else 0

        # Generate HTML
        bill_html = f"""
        <html>
        <head>
            <title>Bill for {customer['first_name']} {customer['last_name']}</title>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h1 {{ color: #333; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
                .total {{ font-weight: bold; font-size: 1.2em; }}
            </style>
        </head>
        <body>
            <h1>CourierPro Invoice</h1>
            <h2>Customer Details</h2>
            <p><strong>Name:</strong> {customer['first_name']} {customer['last_name']}</p>
            <p><strong>Email:</strong> {customer['email']}</p>
            <p><strong>Address:</strong> {customer['address']}</p>
            
            <h2>Shipments</h2>
            <table>
                <tr>
                    <th>Tracking #</th>
                    <th>Type</th>
                    <th>Weight</th>
                    <th>Priority</th>
                    <th>Recipient</th>
                    <th>Amount</th>
                </tr>
                {"".join(f"""
                <tr>
                    <td>{courier['tracking_number']}</td>
                    <td>{courier['type']}</td>
                    <td>{courier['weight']} kg</td>
                    <td>{courier['priority']}</td>
                    <td>{courier['recipient_name']}<br>{courier['recipient_address']}</td>
                    <td>₹{courier['amount']:.2f}</td>
                </tr>
                """ for courier in couriers)}
                <tr class="total">
                    <td colspan="5">Total Due</td>
                    <td>₹{total_due:.2f}</td>
                </tr>
            </table>
            <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """

        # Generate PDF
        return bill_html

    except Exception as e:
        return f"Error generating bill: {str(e)}", 500
    finally:
        cur.close()
        conn.close()

@app.route("/billing-details/<int:customer_id>")
def billing_details(customer_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    
    try:
        # Get customer details
        cur.execute("SELECT * FROM Customers WHERE customer_id = %s", (customer_id,))
        customer = cur.fetchone()
        
        if not customer:
            return jsonify({"success": False, "message": "Customer not found"})
        
        # Get all couriers for this customer with details
        cur.execute("""
            SELECT 
                C.courier_id,
                P.tracking_number,
                P.type,
                P.weight,
                P.priority,
                P.status,
                (pr.base_fee + (P.weight * pr.rate_per_kg)) AS amount,
                R.first_name AS recipient_first_name,
                R.last_name AS recipient_last_name,
                R.address AS recipient_address
            FROM Couriers C
            JOIN Packages P ON C.package_id = P.package_id
            JOIN Recipients R ON C.recipient_id = R.recipient_id
            JOIN Pricing pr ON P.priority = pr.priority
            WHERE C.customer_id = %s
        """, (customer_id,))
        couriers = cur.fetchall()
        
        # Calculate total due
        total_due = sum(courier['amount'] for courier in couriers)
        
        # Format response
        response = {
            "customer": customer,
            "couriers": [{
                "tracking_number": c["tracking_number"],
                "type": c["type"],
                "weight": c["weight"],
                "priority": c["priority"],
                "status": c["status"],
                "amount": float(c["amount"]),
                "recipient": {
                    "first_name": c["recipient_first_name"],
                    "last_name": c["recipient_last_name"],
                    "address": c["recipient_address"]
                }
            } for c in couriers],
            "total_due": float(total_due)
        }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        cur.close()
        conn.close()


@app.route('/get-my-shipments')
def get_my_shipments():
    if 'user_id' not in session:
        return jsonify([])

    customer_id = get_customer_id(session['user_id'])
    if not customer_id:
        return jsonify([])

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT 
                P.tracking_number, 
                P.type,
                (pr.base_fee + (P.weight * pr.rate_per_kg)) AS amount
            FROM Couriers C
            JOIN Packages P ON C.package_id = P.package_id
            JOIN Pricing pr ON P.priority = pr.priority
            WHERE C.customer_id = %s
            ORDER BY P.date DESC
        """, (customer_id,))
        return jsonify(cur.fetchall())
    except Exception as e:
        return jsonify([])
    finally:
        cur.close()
        conn.close()

@app.route('/shipment-details/<tracking_number>')
def shipment_details(tracking_number):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute("""
            SELECT 
                P.tracking_number,
                P.type,
                P.weight,
                P.priority,
                P.status,
                (pr.base_fee + (P.weight * pr.rate_per_kg)) AS amount,
                R.first_name,
                R.last_name,
                R.address
            FROM Packages P
            JOIN Couriers C ON C.package_id = P.package_id
            JOIN Recipients R ON C.recipient_id = R.recipient_id
            JOIN Pricing pr ON P.priority = pr.priority
            WHERE P.tracking_number = %s
        """, (tracking_number,))
        result = cur.fetchone()
        
        if not result:
            return jsonify({"success": False, "message": "Shipment not found"}), 404
            
        return jsonify({
            "tracking_number": result["tracking_number"],
            "type": result["type"],
            "weight": result["weight"],
            "priority": result["priority"],
            "status": result["status"],
            "amount": float(result["amount"]),
            "recipient": {
                "first_name": result["first_name"],
                "last_name": result["last_name"],
                "address": result["address"]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ========== Run Server ==========
if __name__ == "__main__":
    app.run(debug=True, port=5000)
