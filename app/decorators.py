from functools import wraps
from flask import session, redirect, url_for, flash


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Please log in as admin to access this page.", "error")
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return wrapped


def buyer_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("buyer_id"):
            flash("Please log in to access this page.", "error")
            return redirect(url_for("base.login"))
        return f(*args, **kwargs)
    return wrapped