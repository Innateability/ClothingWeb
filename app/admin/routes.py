from flask import (Blueprint, render_template, request,
                   redirect, url_for, session, flash, current_app)
from app.models import (Admin, Product, ProductType, ProductKind,
                        ProductImage, Order, Payment, Color)
from app import db
from app.utils import save_image
from app.decorators import admin_required
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def get_admin():
    return db.session.get(Admin, session.get("admin_id"))


def get_or_create_color(name):
    """Get existing color by name or create it if it doesn't exist."""
    name = name.strip()
    if not name:
        return None
    color = Color.query.filter_by(name=name).first()
    if not color:
        color = Color(name=name)
        db.session.add(color)
        db.session.flush()
    return color


# ── AUTH ──────────────────────────────────────────────────────

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email")
        password = request.form.get("password")
        admin    = Admin.query.filter_by(email=email).first()

        if not admin or not check_password_hash(admin.password, password):
            flash("Invalid credentials.", "error")
            return redirect(url_for("admin.login"))

        session["admin_id"]   = admin.id
        session["admin_name"] = admin.name
        flash("Welcome back, Admin.", "success")
        return redirect(url_for("admin.dashboard"))

    return render_template("admin/login.html")


@admin_bp.route("/logout")
def logout():
    session.pop("admin_id",   None)
    session.pop("admin_name", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/setup", methods=["GET", "POST"])
def setup():
    if Admin.query.first():
        flash("Admin already exists.", "error")
        return redirect(url_for("admin.login"))

    if request.method == "POST":
        admin = Admin(
            name=request.form.get("name"),
            email=request.form.get("email"),
            password=generate_password_hash(request.form.get("password")),
            account_number=request.form.get("account_number"),
            account_name=request.form.get("account_name"),
            bank_name=request.form.get("bank_name"),
            phone=request.form.get("phone"),
        )
        db.session.add(admin)
        db.session.commit()
        flash("Admin account created. Please log in.", "success")
        return redirect(url_for("admin.login"))

    return render_template("admin/setup.html")


# ── DASHBOARD ─────────────────────────────────────────────────

@admin_bp.route("/")
@admin_required
def dashboard():
    admin            = get_admin()
    total_products   = Product.query.filter_by(is_active=True).count()
    pending_orders   = Order.query.filter_by(status="pending").count()
    confirmed_orders = Order.query.filter_by(status="confirmed").count()
    recent_orders    = Order.query.order_by(Order.created_at.desc()).limit(10).all()

    return render_template("admin/dashboard.html",
        admin=admin,
        total_products=total_products,
        pending_orders=pending_orders,
        confirmed_orders=confirmed_orders,
        recent_orders=recent_orders,
        admin_name=session.get("admin_name")
    )


# ── PRODUCTS ──────────────────────────────────────────────────

@admin_bp.route("/products")
@admin_required
def products():
    admin        = get_admin()
    all_products = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).all()
    return render_template("admin/products.html",
        products=all_products,
        admin=admin,
        admin_name=session.get("admin_name")
    )


@admin_bp.route("/products/add", methods=["GET", "POST"])
@admin_required
def add_product():
    admin  = get_admin()
    types  = ProductType.query.all()
    # types  = ["Sneakers","Flat shoe"]
    folder = current_app.config["UPLOAD_FOLDER"]

    if request.method == "POST":
        sizes_raw = request.form.getlist("sizes")
        sizes     = ",".join(s.strip() for s in sizes_raw if s.strip())
        kind_id   = request.form.get("kind_id")

        product = Product(
            name=request.form.get("name"),
            description=request.form.get("description"),
            price=float(request.form.get("price")),
            gender=request.form.get("gender"),
            sizes=sizes,
            stock=int(request.form.get("stock", 0)),
            product_type_id=int(request.form.get("product_type_id")),
            kind_id=int(kind_id) if kind_id else None,
            admin_id=session["admin_id"],
            on_sale=False,
            is_active=True,
        )

        # Handle multiple colors
        color_names = request.form.getlist("colors[]")
        for name in color_names:
            name = name.strip()
            if name:
                color = get_or_create_color(name)
                if color:
                    product.colors.append(color)

        db.session.add(product)
        db.session.flush()

        # Handle image uploads
        images   = request.files.getlist("images")
        print(images)
        is_first = True
        for img_file in images:
            filename = save_image(img_file, folder)
            if filename:
                print("yeah")
                db.session.add(ProductImage(
                    filename=filename,
                    product_id=product.id,
                    is_primary=is_first
                ))
                is_first = False

        db.session.commit()
        flash("Product added successfully.", "success")
        return redirect(url_for("admin.products"))

    return render_template("admin/add_product.html",
        types=types,
        admin=admin,
        admin_name=session.get("admin_name")
    )


@admin_bp.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
@admin_required
def edit_product(product_id):
    product = db.get_or_404(Product, product_id)
    admin   = get_admin()
    types   = ProductType.query.all()
    folder  = current_app.config["UPLOAD_FOLDER"]

    if request.method == "POST":
        sizes_raw = request.form.getlist("sizes")
        kind_id   = request.form.get("kind_id")

        product.name            = request.form.get("name")
        product.description     = request.form.get("description")
        product.price           = float(request.form.get("price"))
        product.gender          = request.form.get("gender")
        product.sizes           = ",".join(s.strip() for s in sizes_raw if s.strip())
        product.stock           = int(request.form.get("stock", 0))
        product.product_type_id = int(request.form.get("product_type_id"))
        product.kind_id         = int(kind_id) if kind_id else None
        product.is_active       = request.form.get("is_active") == "on"
        product.updated_at      = datetime.utcnow()

        # Sale pricing
        on_sale        = request.form.get("on_sale") == "on"
        sale_price_raw = request.form.get("sale_price")
        if on_sale and sale_price_raw:
            product.on_sale    = True
            product.sale_price = float(sale_price_raw)
            product.old_price  = product.price
        else:
            product.on_sale    = False
            product.sale_price = None

        # Replace colors with new list
        product.colors = []
        color_names = request.form.getlist("colors[]")
        for name in color_names:
            name = name.strip()
            if name:
                color = get_or_create_color(name)
                if color and color not in product.colors:
                    product.colors.append(color)

        # New image uploads
        for img_file in request.files.getlist("images"):
            filename = save_image(img_file, folder)
            if filename:
                db.session.add(ProductImage(
                    filename=filename,
                    product_id=product.id,
                    is_primary=False
                ))

        db.session.commit()
        flash("Product updated.", "success")
        return redirect(url_for("admin.products"))

    return render_template("admin/edit_product.html",
        product=product,
        types=types,
        admin=admin,
        admin_name=session.get("admin_name")
    )


@admin_bp.route("/products/delete/<int:product_id>", methods=["POST"])
@admin_required
def delete_product(product_id):
    product = db.get_or_404(Product, product_id)
    product.is_active = False
    db.session.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.route("/products/toggle-sale/<int:product_id>", methods=["POST"])
@admin_required
def toggle_sale(product_id):
    product    = db.get_or_404(Product, product_id)
    sale_price = request.form.get("sale_price")

    if product.on_sale:
        product.on_sale    = False
        product.sale_price = None
        flash("Sale removed.", "success")
    else:
        if not sale_price:
            flash("Please provide a sale price.", "error")
            return redirect(url_for("admin.products"))
        product.on_sale    = True
        product.sale_price = float(sale_price)
        product.old_price  = product.price
        flash("Sale activated.", "success")

    db.session.commit()
    return redirect(url_for("admin.products"))


@admin_bp.route("/products/delete-image/<int:image_id>", methods=["POST"])
@admin_required
def delete_image(image_id):
    img        = db.get_or_404(ProductImage, image_id)
    product_id = img.product_id
    db.session.delete(img)
    db.session.commit()
    flash("Image deleted.", "success")
    return redirect(url_for("admin.edit_product", product_id=product_id))


@admin_bp.route("/products/set-primary/<int:image_id>", methods=["POST"])
@admin_required
def set_primary_image(image_id):
    img = db.get_or_404(ProductImage, image_id)
    for other in img.product.images:
        other.is_primary = False
    img.is_primary = True
    db.session.commit()
    flash("Primary image updated.", "success")
    return redirect(url_for("admin.edit_product", product_id=img.product_id))


# ── CATEGORIES ────────────────────────────────────────────────

@admin_bp.route("/categories")
@admin_required
def categories():
    admin  = get_admin()
    types  = ProductType.query.all()
    colors = Color.query.order_by(Color.name).all()
    return render_template("admin/categories.html",
        types=types,
        colors=colors,
        admin=admin,
        admin_name=session.get("admin_name")
    )


@admin_bp.route("/categories/add-type", methods=["POST"])
@admin_required
def add_type():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name required.", "error")
        return redirect(url_for("admin.categories"))
    if ProductType.query.filter_by(name=name).first():
        flash("Type already exists.", "error")
        return redirect(url_for("admin.categories"))
    db.session.add(ProductType(name=name))
    db.session.commit()
    flash(f"Type '{name}' added.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.route("/categories/delete-type/<int:type_id>", methods=["POST"])
@admin_required
def delete_type(type_id):
    pt = db.get_or_404(ProductType, type_id)
    db.session.delete(pt)
    db.session.commit()
    flash("Product type deleted.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.route("/categories/add-kind", methods=["POST"])
@admin_required
def add_kind():
    name    = request.form.get("name", "").strip()
    type_id = request.form.get("type_id", type=int)
    if not name or not type_id:
        flash("All fields required.", "error")
        return redirect(url_for("admin.categories"))
    db.session.add(ProductKind(name=name, product_type_id=type_id))
    db.session.commit()
    flash(f"Kind '{name}' added.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.route("/categories/delete-kind/<int:kind_id>", methods=["POST"])
@admin_required
def delete_kind(kind_id):
    kind = db.get_or_404(ProductKind, kind_id)
    db.session.delete(kind)
    db.session.commit()
    flash("Kind deleted.", "success")
    return redirect(url_for("admin.categories"))


# ── ORDERS ────────────────────────────────────────────────────

@admin_bp.route("/orders")
@admin_required
def orders():
    admin      = get_admin()
    status     = request.args.get("status", "pending")
    all_orders = Order.query.filter_by(status=status).order_by(
        Order.created_at.desc()
    ).all()
    return render_template("admin/orders.html",
        orders=all_orders,
        status=status,
        admin=admin,
        admin_name=session.get("admin_name")
    )


@admin_bp.route("/orders/<int:order_id>")
@admin_required
def order_detail(order_id):
    admin = get_admin()
    order = db.get_or_404(Order, order_id)
    return render_template("admin/order_detail.html",
        order=order,
        admin=admin,
        admin_name=session.get("admin_name")
    )


@admin_bp.route("/orders/<int:order_id>/confirm", methods=["POST"])
@admin_required
def confirm_payment(order_id):
    order        = db.get_or_404(Order, order_id)
    order.status = "confirmed"
    if order.payment:
        order.payment.confirmed    = True
        order.payment.confirmed_at = datetime.utcnow()
        order.payment.admin_id     = session["admin_id"]
    db.session.commit()
    flash(f"Order #{order.id} confirmed.", "success")
    return redirect(url_for("admin.orders"))


@admin_bp.route("/orders/<int:order_id>/reject", methods=["POST"])
@admin_required
def reject_payment(order_id):
    order        = db.get_or_404(Order, order_id)
    order.status = "rejected"
    db.session.commit()
    flash(f"Order #{order.id} rejected.", "success")
    return redirect(url_for("admin.orders"))


# ── SETTINGS ──────────────────────────────────────────────────

@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    admin = get_admin()

    if request.method == "POST":
        admin.name           = request.form.get("name")
        admin.phone          = request.form.get("phone")
        admin.account_number = request.form.get("account_number")
        admin.account_name   = request.form.get("account_name")
        admin.bank_name      = request.form.get("bank_name")

        new_password = request.form.get("new_password")
        if new_password:
            admin.password = generate_password_hash(new_password)

        db.session.commit()
        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))

    return render_template("admin/settings.html",
        admin=admin,
        admin_name=session.get("admin_name")
    )