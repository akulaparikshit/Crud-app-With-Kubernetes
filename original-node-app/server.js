
const express = require("express");
const path = require("path");
const { Pool } = require("pg");

const app = express();
const PORT = process.env.PORT || 3000;

// PostgreSQL connection
const pool = new Pool({
  host: process.env.DB_HOST || "localhost",
  port: Number(process.env.DB_PORT || 5432),
  user: process.env.DB_USER || "cruduser",
  password: process.env.DB_PASSWORD || "crudpassword",
  database: process.env.DB_NAME || "cruddb"
});

app.use(express.json());

// Serve the website
app.get("/", (req, res) => {
  res.sendFile(path.join(__dirname, "index.html"));
});

// Create products table
const initializeDatabase = async () => {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS products (
      id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
      name TEXT NOT NULL,
      quantity INTEGER NOT NULL DEFAULT 0
        CHECK (quantity >= 0),
      price NUMERIC(10, 2) NOT NULL
        CHECK (price >= 0)
    )
  `);
};

// CREATE - Add a product
app.post("/api/products", async (req, res) => {
  const name = String(req.body.name || "").trim();
  const quantity = Number(req.body.quantity);
  const price = Number(req.body.price);

  if (
    !name ||
    req.body.quantity === undefined ||
    req.body.price === undefined ||
    !Number.isInteger(quantity) ||
    quantity < 0 ||
    !Number.isFinite(price) ||
    price < 0
  ) {
    return res.status(400).json({
      error: "Enter a valid name, quantity and price"
    });
  }

  try {
    const result = await pool.query(
      `INSERT INTO products (name, quantity, price)
       VALUES ($1, $2, $3)
       RETURNING id, name, quantity, price`,
      [name, quantity, price]
    );

    res.status(201).json({
      ...result.rows[0],
      id: String(result.rows[0].id)
    });
  } catch (error) {
    console.error("Add product error:", error.message);
    res.status(500).json({ error: "Could not add product" });
  }
});

// READ - View all products
app.get("/api/products", async (req, res) => {
  try {
    const result = await pool.query(
      "SELECT id, name, quantity, price FROM products ORDER BY id"
    );

    res.json(result.rows.map(product => ({
      ...product,
      id: String(product.id),
      price: Number(product.price)
    })));
  } catch (error) {
    console.error("Read products error:", error.message);
    res.status(500).json({ error: "Could not read products" });
  }
});

// READ - View one product
app.get("/api/products/:id", async (req, res) => {
  const { id } = req.params;

  if (!/^\d+$/.test(id)) {
    return res.status(400).json({ error: "Invalid product ID" });
  }

  try {
    const result = await pool.query(
      "SELECT id, name, quantity, price FROM products WHERE id = $1",
      [id]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({ error: "Product not found" });
    }

    res.json({
      ...result.rows[0],
      id: String(result.rows[0].id),
      price: Number(result.rows[0].price)
    });
  } catch (error) {
    console.error("View product error:", error.message);
    res.status(500).json({ error: "Could not view product" });
  }
});

// UPDATE - Update stock quantity
app.put("/api/products/:id", async (req, res) => {
  const { id } = req.params;
  const quantity = Number(req.body.quantity);

  if (!/^\d+$/.test(id)) {
    return res.status(400).json({ error: "Invalid product ID" });
  }

  if (
    req.body.quantity === undefined ||
    !Number.isInteger(quantity) ||
    quantity < 0
  ) {
    return res.status(400).json({
      error: "Enter a valid stock quantity"
    });
  }

  try {
    const result = await pool.query(
      `UPDATE products
       SET quantity = $1
       WHERE id = $2
       RETURNING id, name, quantity, price`,
      [quantity, id]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({ error: "Product not found" });
    }

    res.json({
      ...result.rows[0],
      id: String(result.rows[0].id),
      price: Number(result.rows[0].price)
    });
  } catch (error) {
    console.error("Update stock error:", error.message);
    res.status(500).json({ error: "Could not update stock" });
  }
});

// DELETE - Remove a product
app.delete("/api/products/:id", async (req, res) => {
  const { id } = req.params;

  if (!/^\d+$/.test(id)) {
    return res.status(400).json({ error: "Invalid product ID" });
  }

  try {
    const result = await pool.query(
      "DELETE FROM products WHERE id = $1 RETURNING id",
      [id]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({ error: "Product not found" });
    }

    res.json({ message: "Product deleted successfully" });
  } catch (error) {
    console.error("Delete product error:", error.message);
    res.status(500).json({ error: "Could not delete product" });
  }
});

// Start server after database initialization
initializeDatabase()
  .then(() => {
    app.listen(PORT, "0.0.0.0", () => {
      console.log(`Inventory Management System running on port ${PORT}`);
      console.log("Connected to PostgreSQL");
    });
  })
  .catch(error => {
    console.error("Database initialization failed:", error.message);
    process.exit(1);
  });

// Graceful shutdown
process.on("SIGTERM", async () => {
  await pool.end();
  process.exit(0);
});
