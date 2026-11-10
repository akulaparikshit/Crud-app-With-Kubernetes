import math
import os
import re
import threading

import mysql.connector
from flask import Flask, jsonify, request, send_from_directory
from mysql.connector.pooling import MySQLConnectionPool

app = Flask(__name__)

db_pool = None
pool_lock = threading.Lock()

# Same rule as the original Node app: an id must be digits only, otherwise 400.
ID_PATTERN = re.compile(r"^\d+$")


# DATABASE CONNECTION
# The pool (and the products table) is created on the first request, not at
# import time, so the app still starts if MySQL is not ready yet.
#
# Pool size = gunicorn threads per worker. Each worker process has its own pool
# and can never run more requests at once than it has threads, so the pool can
# never run dry (mysql-connector raises PoolError immediately when it is empty).
def get_db():
    global db_pool
    if db_pool is None:
        with pool_lock:
            if db_pool is None:
                pool = MySQLConnectionPool(
                    pool_name="crud_pool",
                    pool_size=int(os.getenv("DB_POOL_SIZE",
                                            os.getenv("GUNICORN_THREADS", "4"))),
                    # autocommit: every statement is its own transaction, so a
                    # pooled connection never holds an old read snapshot. That
                    # makes the per-checkout session reset (an extra round trip
                    # to MySQL on every request) unnecessary.
                    autocommit=True,
                    pool_reset_session=False,
                    host=os.getenv("DB_HOST", "localhost"),
                    port=int(os.getenv("DB_PORT", "3306")),
                    user=os.getenv("DB_USER", "cruduser"),
                    password=os.getenv("DB_PASSWORD", "crudpassword"),
                    database=os.getenv("DB_NAME", "cruddb"),
                )
                conn = pool.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS products (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        name TEXT NOT NULL,
                        quantity INT NOT NULL DEFAULT 0 CHECK (quantity >= 0),
                        price DECIMAL(10,2) NOT NULL CHECK (price >= 0)
                    )
                """)
                cursor.close()
                conn.close()
                db_pool = pool
    return db_pool.get_connection()


def to_json(row):
    return {"id": str(row[0]), "name": row[1],
            "quantity": row[2], "price": float(row[3])}


def parse_quantity(value):
    # Whole numbers >= 0 only (rejects true/false, 5.5, "abc", -1)
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise ValueError()
    quantity = int(value)
    if quantity < 0:
        raise ValueError()
    return quantity


def invalid_id():
    return jsonify({"error": "Invalid product ID"}), 400


def db_error(action):
    app.logger.exception("Database error while %s", action)
    return jsonify({"error": f"Could not {action}"}), 500


# HOME PAGE
@app.route("/")
def home():
    return send_from_directory("templates", "index.html")


# HEALTH CHECK (used by Docker and Kubernetes probes)
# Deliberately does not touch MySQL: if the database is down, restarting the
# Flask container would not fix it, and the API already answers 500 with a
# clear message. The probe checks that this process can still serve requests.
@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


# CREATE - Add a product
@app.route("/api/products", methods=["POST"])
def add_product():
    data = request.get_json(silent=True) or {}
    try:
        name = str(data.get("name") or "").strip()
        quantity = parse_quantity(data["quantity"])
        if isinstance(data["price"], bool):
            raise ValueError()
        price = float(data["price"])
        if not name or not math.isfinite(price) or price < 0:
            raise ValueError()
    except (KeyError, TypeError, ValueError, OverflowError):
        return jsonify({"error": "Enter a valid name, quantity and price"}), 400

    db = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO products (name, quantity, price) VALUES (%s, %s, %s)",
            (name, quantity, price),
        )
        product_id = cursor.lastrowid
        cursor.close()
        return jsonify({"id": str(product_id), "name": name,
                        "quantity": quantity, "price": round(price, 2)}), 201
    except mysql.connector.Error:
        return db_error("add product")
    finally:
        if db:
            db.close()


# READ - View all products
@app.route("/api/products", methods=["GET"])
def get_products():
    db = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT id, name, quantity, price FROM products ORDER BY id")
        rows = cursor.fetchall()
        cursor.close()
        return jsonify([to_json(row) for row in rows]), 200
    except mysql.connector.Error:
        return db_error("read products")
    finally:
        if db:
            db.close()


# READ - View one product
@app.route("/api/products/<product_id>", methods=["GET"])
def get_product(product_id):
    if not ID_PATTERN.match(product_id):
        return invalid_id()
    db = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT id, name, quantity, price FROM products WHERE id = %s",
            (product_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return jsonify({"error": "Product not found"}), 404
        return jsonify(to_json(row)), 200
    except mysql.connector.Error:
        return db_error("view product")
    finally:
        if db:
            db.close()


# UPDATE - Update stock quantity
@app.route("/api/products/<product_id>", methods=["PUT"])
def update_product(product_id):
    if not ID_PATTERN.match(product_id):
        return invalid_id()
    data = request.get_json(silent=True) or {}
    try:
        quantity = parse_quantity(data["quantity"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return jsonify({"error": "Enter a valid stock quantity"}), 400

    db = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE products SET quantity = %s WHERE id = %s",
            (quantity, product_id),
        )
        # MySQL reports 0 changed rows when the value is the same,
        # so we check if the product exists with a SELECT instead.
        cursor.execute(
            "SELECT id, name, quantity, price FROM products WHERE id = %s",
            (product_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return jsonify({"error": "Product not found"}), 404
        return jsonify(to_json(row)), 200
    except mysql.connector.Error:
        return db_error("update stock")
    finally:
        if db:
            db.close()


# DELETE - Remove a product
@app.route("/api/products/<product_id>", methods=["DELETE"])
def delete_product(product_id):
    if not ID_PATTERN.match(product_id):
        return invalid_id()
    db = None
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
        deleted = cursor.rowcount
        cursor.close()
        if deleted == 0:
            return jsonify({"error": "Product not found"}), 404
        return jsonify({"message": "Product deleted successfully"}), 200
    except mysql.connector.Error:
        return db_error("delete product")
    finally:
        if db:
            db.close()


# Local development only - in Docker/Kubernetes gunicorn runs the app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
