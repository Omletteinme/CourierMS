from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import mysql.connector
import os
import random
import string
from datetime import datetime

app = Flask(__name__, static_folder='.')
CORS(app)

# DB Connection
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="CourierDB"
    )

# Serve Pages
@app.route('/')
def home():
    return send_from_directory('.', 'index1.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

# ========== AUTH ==========
@app.route("/signup", methods=["POST"])
def signup():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.callproc("AddUser", (data["username"], data["password"]))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        cur.close()
        conn.close()

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.callproc("LoginUser", (data["username"], data["password"]))
    user = None
    for result in cur.stored_results():
        user = result.fetchone()
    cur.close()
    conn.close()
    return jsonify({"success": bool(user), "user": user if user else None})

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

# ========== PACKAGE ==========
@app.route("/add-package", methods=["POST"])
def add_package():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.callproc("AddPackage", (data["description"], data["weight"], data["dimensions"], data["value"]))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})

# ========== COURIER ==========

@app.route("/create-courier", methods=["POST"])
def create_courier():
    data = request.json
    conn = get_db()
    cur = conn.cursor()

    try:
        # 1. Insert Customer
        cust = data["customer"]
        cur.execute("""
            INSERT INTO Customers (first_name, last_name, phone, email, address)
            VALUES (%s, %s, %s, %s, %s)
        """, (cust["first_name"], cust["last_name"], cust["phone"], cust["email"], cust["address"]))
        customer_id = cur.lastrowid

        # 2. Insert Recipient
        rec = data["recipient"]
        cur.execute("""
            INSERT INTO Recipients (first_name, last_name, phone, email, address)
            VALUES (%s, %s, %s, %s, %s)
        """, (rec["first_name"], rec["last_name"], rec["phone"], rec["email"], rec["address"]))
        recipient_id = cur.lastrowid

        # 3. Insert Package
        pack = data["package"]
        tracking_number = "TRK" + ''.join(random.choices(string.digits, k=8))
        created_at = datetime.now()
        cur.execute("""
            INSERT INTO Packages (customer_id, recipient_id, weight, type, priority, status, tracking_number, date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (customer_id, recipient_id, pack["weight"], pack["type"], pack["priority"], pack["status"], tracking_number, created_at))
        package_id = cur.lastrowid

        # 4. Insert into Couriers (main entry)
        cur.execute("""
            INSERT INTO Couriers (customer_id, recipient_id, package_id, status, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (customer_id, recipient_id, package_id, pack["status"], created_at))

        conn.commit()
        return jsonify({"success": True, "tracking_number": tracking_number, "message": f"Courier created. Tracking #: {tracking_number}"})
    
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})

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
    cur.callproc("GetAllCouriers")
    couriers = []
    for r in cur.stored_results():
        couriers = r.fetchall()
    cur.close()
    conn.close()
    return jsonify(couriers)

@app.route("/update-status", methods=["POST"])
def update_status():
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    cur.callproc("UpdateCourierStatus", (data["courier_id"], data["new_status"]))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})

# ========== PAYMENT ==========
@app.route("/make-payment/<tracking_number>", methods=["POST"])
def make_payment_for_tracking(tracking_number):
    conn = get_db()
    cur = conn.cursor()

    try:
        # Get package and courier details
        cur.execute("""
            SELECT P.priority, C.courier_id, C.customer_id
            FROM Packages P
            JOIN Couriers C ON C.package_id = P.package_id
            WHERE P.tracking_number = %s
        """, (tracking_number,))
        result = cur.fetchone()

        if not result:
            return jsonify({"success": False, "message": "Tracking number not found"})

        priority, courier_id, customer_id = result

        price_map = {"Low": 100, "Medium": 250, "High": 500}
        amount = price_map.get(priority, 100)

        # Insert payment
        cur.execute("""
            INSERT INTO Payments (courier_id, amount, method)
            VALUES (%s, %s, %s)
        """, (courier_id, amount, "Online"))

        # Optionally update Billing table
        cur.execute("""
            INSERT INTO Billing (customer_id, total_amount, billing_date)
            VALUES (%s, %s, CURDATE())
            ON DUPLICATE KEY UPDATE total_amount = total_amount + VALUES(total_amount)
        """, (customer_id, amount))

        conn.commit()
        return jsonify({"success": True, "message": f"Payment of ₹{amount} successful for {priority} priority."})

    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})

    finally:
        cur.close()
        conn.close()

# ========== BILLING ==========
@app.route("/generate-bill/<int:customer_id>", methods=["POST"])
def generate_bill(customer_id):
    conn = get_db()
    cur = conn.cursor()
    cur.callproc("GenerateBill", (customer_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True})

@app.route("/billing/<int:customer_id>")
def view_bill(customer_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT SUM(P.amount) as total FROM Payments P
        JOIN Couriers C ON C.courier_id = P.courier_id
        WHERE C.customer_id = %s
    """, (customer_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return jsonify({"customer_id": customer_id, "total_due": result["total"] if result["total"] else 0})

# Run Server
if __name__ == "__main__":
    app.run(debug=True, port=5000)
