from app import db
from datetime import datetime, timedelta


# Many-to-many association table between Product and Color
product_colors = db.Table(
    "product_colors",
    db.Column("product_id", db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    db.Column("color_id",   db.Integer, db.ForeignKey("colors.id",   ondelete="CASCADE"), primary_key=True),
)


class Admin(db.Model):
    __tablename__ = "admins"
    id             = db.Column(db.Integer, primary_key=True)
    email          = db.Column(db.String(150), unique=True, nullable=False)
    password       = db.Column(db.String(300), nullable=False)
    name           = db.Column(db.String(150), nullable=False)
    account_number = db.Column(db.String(50),  nullable=False)
    account_name   = db.Column(db.String(150), nullable=False)
    bank_name      = db.Column(db.String(150), nullable=False)
    phone          = db.Column(db.String(30),  nullable=False)

    products = db.relationship("Product", back_populates="admin", cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="admin")


class Buyer(db.Model):
    __tablename__ = "buyers"
    id       = db.Column(db.Integer, primary_key=True)
    email    = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(300), nullable=False)
    name     = db.Column(db.String(150), nullable=False)
    phone    = db.Column(db.String(30),  nullable=True)

    cart_items = db.relationship("CartItem", back_populates="buyer", cascade="all, delete-orphan")
    orders     = db.relationship("Order",    back_populates="buyer", cascade="all, delete-orphan")


class ProductType(db.Model):
    __tablename__ = "product_types"
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

    kinds    = db.relationship("ProductKind", back_populates="product_type", cascade="all, delete-orphan")
    products = db.relationship("Product",     back_populates="product_type")


class ProductKind(db.Model):
    __tablename__ = "product_kinds"
    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(100), nullable=False)
    product_type_id = db.Column(
        db.Integer,
        db.ForeignKey("product_types.id", ondelete="CASCADE"),
        nullable=False
    )

    product_type = db.relationship("ProductType", back_populates="kinds")
    products     = db.relationship("Product",     back_populates="kind")


class Color(db.Model):
    __tablename__ = "colors"
    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)

    products = db.relationship("Product", secondary=product_colors, back_populates="colors")


class Product(db.Model):
    __tablename__ = "products"
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text,        nullable=True)
    price       = db.Column(db.Numeric(10, 2), nullable=False)
    old_price   = db.Column(db.Numeric(10, 2), nullable=True)
    on_sale     = db.Column(db.Boolean, default=False)
    sale_price  = db.Column(db.Numeric(10, 2), nullable=True)
    gender      = db.Column(db.String(20),  nullable=False)
    sizes       = db.Column(db.String(200), nullable=True)
    stock       = db.Column(db.Integer, default=0)
    is_active   = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product_type_id = db.Column(db.Integer, db.ForeignKey("product_types.id"), nullable=False)
    kind_id         = db.Column(db.Integer, db.ForeignKey("product_kinds.id"), nullable=True)
    admin_id        = db.Column(db.Integer, db.ForeignKey("admins.id"),        nullable=False)

    product_type = db.relationship("ProductType", back_populates="products")
    kind         = db.relationship("ProductKind", back_populates="products")
    admin        = db.relationship("Admin",        back_populates="products")
    images       = db.relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")
    cart_items   = db.relationship("CartItem",     back_populates="product")
    order_items  = db.relationship("OrderItem",    back_populates="product")
    colors       = db.relationship("Color", secondary=product_colors, back_populates="products")

    def effective_price(self):
        if self.on_sale and self.sale_price:
            return self.sale_price
        return self.price

    def get_sizes(self):
        if self.sizes:
            return [s.strip() for s in self.sizes.split(",")]
        return []

    def get_colors(self):
        return [c.name for c in self.colors]

    def primary_image(self):
        for img in self.images:
            if img.is_primary:
                return img.filename
        if self.images:
            return self.images[0].filename
        return None


class ProductImage(db.Model):
    __tablename__ = "product_images"
    id         = db.Column(db.Integer, primary_key=True)
    filename   = db.Column(db.String(300), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False
    )

    product = db.relationship("Product", back_populates="images")


class CartItem(db.Model):
    __tablename__ = "cart_items"
    id           = db.Column(db.Integer, primary_key=True)
    buyer_id     = db.Column(db.Integer, db.ForeignKey("buyers.id",   ondelete="CASCADE"), nullable=False)
    product_id   = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity     = db.Column(db.Integer, default=1)
    size         = db.Column(db.String(20),     nullable=True)
    price_at_add = db.Column(db.Numeric(10, 2), nullable=False)
    added_at     = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at   = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=30))

    buyer   = db.relationship("Buyer",   back_populates="cart_items")
    product = db.relationship("Product", back_populates="cart_items")

    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    def price_changed(self):
        current = round(float(self.product.effective_price()), 2)
        return current != round(float(self.price_at_add), 2)


class Order(db.Model):
    __tablename__ = "orders"
    id         = db.Column(db.Integer, primary_key=True)
    buyer_id   = db.Column(db.Integer, db.ForeignKey("buyers.id", ondelete="CASCADE"), nullable=False)
    total      = db.Column(db.Numeric(10, 2), nullable=False)
    status     = db.Column(db.String(30), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes      = db.Column(db.Text, nullable=True)

    buyer   = db.relationship("Buyer",     back_populates="orders")
    items   = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payment = db.relationship("Payment",   back_populates="order", uselist=False)


class OrderItem(db.Model):
    __tablename__ = "order_items"
    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey("orders.id",   ondelete="CASCADE"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity   = db.Column(db.Integer, nullable=False)
    size       = db.Column(db.String(20),     nullable=True)
    price      = db.Column(db.Numeric(10, 2), nullable=False)

    order   = db.relationship("Order",   back_populates="items")
    product = db.relationship("Product", back_populates="order_items")


class Payment(db.Model):
    __tablename__ = "payments"
    id           = db.Column(db.Integer, primary_key=True)
    order_id     = db.Column(db.Integer, db.ForeignKey("orders.id",  ondelete="CASCADE"), unique=True, nullable=False)
    admin_id     = db.Column(db.Integer, db.ForeignKey("admins.id"), nullable=False)
    amount       = db.Column(db.Numeric(10, 2), nullable=False)
    confirmed    = db.Column(db.Boolean, default=False)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    buyer_note   = db.Column(db.Text, nullable=True)

    order = db.relationship("Order", back_populates="payment")
    admin = db.relationship("Admin", back_populates="payments")