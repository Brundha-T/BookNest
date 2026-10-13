import os, sqlite3
from pathlib import Path
from functools import wraps
from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

ROOT = Path(__file__).resolve().parent
DB = Path(os.getenv("BOOKNEST_DB", str(ROOT / "data" / "booknest.db")))
DB.parent.mkdir(parents=True, exist_ok=True)
app = Flask(__name__, static_folder=None)
app.secret_key = os.getenv("SECRET_KEY", "dev-only-change-this-secret")

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS books(id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL, category TEXT DEFAULT 'General', total_copies INTEGER NOT NULL, available_copies INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), book_id INTEGER NOT NULL REFERENCES books(id), status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','return_requested','returned')), requested_at TEXT DEFAULT CURRENT_TIMESTAMP, decided_at TEXT, returned_at TEXT, due_at TEXT, admin_note TEXT);
        CREATE TABLE IF NOT EXISTS reservations(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), book_id INTEGER NOT NULL REFERENCES books(id), status TEXT NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting','fulfilled','cancelled')), created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,book_id,status));
        CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY, title TEXT NOT NULL, message TEXT NOT NULL, created_by INTEGER REFERENCES users(id), created_at TEXT DEFAULT CURRENT_TIMESTAMP, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), book_id INTEGER NOT NULL REFERENCES books(id), rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), review TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,book_id));
        """)
        # Safe schema migration for databases created by earlier BookNest versions.
        loan_cols = {row['name'] for row in c.execute("PRAGMA table_info(loans)").fetchall()}
        if 'due_at' not in loan_cols:
            c.execute("ALTER TABLE loans ADD COLUMN due_at TEXT")
        email = os.getenv("ADMIN_EMAIL", "admin@booknest.local").strip().lower()
        password = os.getenv("ADMIN_PASSWORD", "Admin123!")
        if not c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            c.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'admin')", ("BookNest Admin", email, generate_password_hash(password)))
        if c.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 0:
            c.executemany("INSERT INTO books(title,author,category,total_copies,available_copies) VALUES(?,?,?,?,?)", [
                ("Clean Code","Robert C. Martin","Software Engineering",3,3),
                ("The Pragmatic Programmer","Andrew Hunt and David Thomas","Software Engineering",2,2),
                ("Introduction to Algorithms","Thomas H. Cormen et al.","Computer Science",2,2),
                ("Atomic Habits","James Clear","Personal Development",2,2)])

def me():
    if not session.get("user_id"): return None
    with conn() as c:
        r = c.execute("SELECT id,name,email,role FROM users WHERE id=?", (session["user_id"],)).fetchone()
        return dict(r) if r else None

def login_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        u = me()
        if not u: return jsonify(error="Please log in first."), 401
        request.user = u
        return fn(*a, **kw)
    return w

def admin_required(fn):
    @wraps(fn)
    @login_required
    def w(*a, **kw):
        if request.user["role"] != "admin": return jsonify(error="Administrator access required."), 403
        return fn(*a, **kw)
    return w

@app.get("/")
def home(): return send_from_directory(ROOT, "welcome.html")

@app.get("/login")
def login_page(): return send_from_directory(ROOT, "login.html")

@app.get("/signup")
def signup_page(): return send_from_directory(ROOT, "signup.html")

@app.get("/dashboard")
def dashboard_page():
    if not me():
        from flask import redirect
        return redirect("/login")
    return send_from_directory(ROOT, "index.html")

@app.get("/health")
def health(): return jsonify(status="ok", service="BookNest")

@app.get("/api/me")
def whoami(): return jsonify(user=me())

@app.post("/api/register")
def register():
    d=request.get_json(silent=True) or {}; name=str(d.get("name","")).strip(); email=str(d.get("email","")).strip().lower(); pw=str(d.get("password",""))
    if not name or not email or len(pw)<8: return jsonify(error="Enter name, email, and a password of at least 8 characters."),400
    try:
        with conn() as c:
            cur=c.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'student')",(name,email,generate_password_hash(pw)))
            session["user_id"]=cur.lastrowid
    except sqlite3.IntegrityError: return jsonify(error="An account with this email already exists."),409
    return jsonify(message="Registration successful.",user=me()),201

@app.post("/api/login")
def login():
    d=request.get_json(silent=True) or {}; email=str(d.get("email","")).strip().lower(); pw=str(d.get("password",""))
    with conn() as c: u=c.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    if not u or not check_password_hash(u["password_hash"],pw): return jsonify(error="Incorrect email or password."),401
    session.clear(); session["user_id"]=u["id"]
    return jsonify(message="Login successful.",user=me())

@app.post("/api/logout")
def logout(): session.clear(); return jsonify(message="Logged out.")

@app.get("/api/books")
def books():
    q="%"+str(request.args.get("q","")).strip()+"%"
    with conn() as c: rows=c.execute("SELECT b.id,b.title,b.author,b.category,b.total_copies,b.available_copies,COALESCE((SELECT ROUND(AVG(r.rating),1) FROM reviews r WHERE r.book_id=b.id),0) AS rating,(SELECT COUNT(*) FROM reviews r WHERE r.book_id=b.id) AS review_count FROM books b WHERE b.title LIKE ? OR b.author LIKE ? OR b.category LIKE ? ORDER BY b.title",(q,q,q)).fetchall()
    return jsonify(books=[dict(r) for r in rows])

@app.post("/api/loans")
@login_required
def request_loan():
    try: bid=int((request.get_json(silent=True) or {}).get("book_id"))
    except (TypeError,ValueError): return jsonify(error="A valid book ID is required."),400
    with conn() as c:
        b=c.execute("SELECT * FROM books WHERE id=?",(bid,)).fetchone()
        if not b: return jsonify(error="Book not found."),404
        if b["available_copies"]<1: return jsonify(error="No copies are available."),409
        old=c.execute("SELECT id FROM loans WHERE user_id=? AND book_id=? AND status IN ('pending','approved','return_requested')",(request.user["id"],bid)).fetchone()
        if old: return jsonify(error="You already have an active request or loan for this book."),409
        c.execute("INSERT INTO loans(user_id,book_id) VALUES(?,?)",(request.user["id"],bid))
    return jsonify(message="Borrowing request sent to admin for approval."),201

@app.get("/api/history")
@login_required
def history():
    with conn() as c:
        rows=c.execute("SELECT l.id,l.status,l.requested_at,l.decided_at,l.returned_at,l.due_at,CASE WHEN l.status='approved' AND l.due_at < CURRENT_TIMESTAMP THEN 1 ELSE 0 END AS overdue,l.admin_note,b.title,b.author FROM loans l JOIN books b ON b.id=l.book_id WHERE l.user_id=? ORDER BY l.requested_at DESC",(request.user["id"],)).fetchall()
    return jsonify(loans=[dict(r) for r in rows])

@app.post("/api/loans/<int:lid>/return")
@login_required
def return_request(lid):
    with conn() as c:
        l=c.execute("SELECT * FROM loans WHERE id=?",(lid,)).fetchone()
        if not l or l["user_id"]!=request.user["id"]: return jsonify(error="Loan not found."),404
        if l["status"]!="approved": return jsonify(error="Only approved loans can be marked for return."),409
        c.execute("UPDATE loans SET status='return_requested' WHERE id=?",(lid,))
    return jsonify(message="Return confirmation sent to admin.")

@app.get("/api/admin/loans")
@admin_required
def admin_loans():
    with conn() as c:
        rows=c.execute("SELECT l.id,l.status,l.requested_at,l.returned_at,l.due_at,CASE WHEN l.status='approved' AND l.due_at < CURRENT_TIMESTAMP THEN 1 ELSE 0 END AS overdue,l.admin_note,b.title,b.author,u.name student_name,u.email student_email FROM loans l JOIN books b ON b.id=l.book_id JOIN users u ON u.id=l.user_id ORDER BY l.requested_at DESC").fetchall()
    return jsonify(loans=[dict(r) for r in rows])

@app.post("/api/admin/loans/<int:lid>/decision")
@admin_required
def decision(lid):
    d=request.get_json(silent=True) or {}; choice=str(d.get("decision","")).lower(); note=str(d.get("note","")).strip()[:300]
    if choice not in ("approve","reject"): return jsonify(error="Decision must be approve or reject."),400
    with conn() as c:
        l=c.execute("SELECT * FROM loans WHERE id=?",(lid,)).fetchone()
        if not l: return jsonify(error="Request not found."),404
        if l["status"]!="pending": return jsonify(error="Only pending requests can be decided."),409
        b=c.execute("SELECT * FROM books WHERE id=?",(l["book_id"],)).fetchone()
        if choice=="approve":
            if b["available_copies"]<1: return jsonify(error="No copies available."),409
            c.execute("UPDATE books SET available_copies=available_copies-1 WHERE id=?",(b["id"],))
            c.execute("UPDATE loans SET status='approved',decided_at=CURRENT_TIMESTAMP,due_at=datetime('now','+14 days'),admin_note=? WHERE id=?",(note or "Approved · due in 14 days",lid))
        else: c.execute("UPDATE loans SET status='rejected',decided_at=CURRENT_TIMESTAMP,admin_note=? WHERE id=?",(note or "Rejected",lid))
    return jsonify(message=f"Request {choice}d successfully.")

@app.post("/api/admin/loans/<int:lid>/confirm-return")
@admin_required
def confirm_return(lid):
    with conn() as c:
        l=c.execute("SELECT * FROM loans WHERE id=?",(lid,)).fetchone()
        if not l: return jsonify(error="Loan not found."),404
        if l["status"]!="return_requested": return jsonify(error="Loan is not awaiting return confirmation."),409
        c.execute("UPDATE loans SET status='returned',returned_at=CURRENT_TIMESTAMP,admin_note='Return confirmed' WHERE id=?",(lid,))
        c.execute("UPDATE books SET available_copies=available_copies+1 WHERE id=?",(l["book_id"],))
    return jsonify(message="Return confirmed and inventory updated.")

@app.post("/api/admin/books")
@admin_required
def add_book():
    d=request.get_json(silent=True) or {}; title=str(d.get("title","")).strip(); author=str(d.get("author","")).strip(); cat=str(d.get("category","General")).strip() or "General"
    try: copies=int(d.get("copies",1))
    except (TypeError,ValueError): copies=0
    if not title or not author or not 1<=copies<=1000: return jsonify(error="Enter title, author, and copies from 1 to 1000."),400
    with conn() as c: c.execute("INSERT INTO books(title,author,category,total_copies,available_copies) VALUES(?,?,?,?,?)",(title,author,cat,copies,copies))
    return jsonify(message="Book added."),201

@app.get("/api/admin/users")
@admin_required
def users():
    with conn() as c: rows=c.execute("SELECT id,name,email,role,created_at FROM users ORDER BY created_at DESC").fetchall()
    return jsonify(users=[dict(r) for r in rows])

@app.put("/api/admin/books/<int:bid>")
@admin_required
def update_book(bid):
    d=request.get_json(silent=True) or {}
    title=str(d.get("title","")).strip(); author=str(d.get("author","")).strip(); category=str(d.get("category","General")).strip() or "General"
    try: copies=int(d.get("copies",0))
    except (TypeError,ValueError): copies=0
    if not title or not author or not 1<=copies<=1000:
        return jsonify(error="Enter title, author, and total copies from 1 to 1000."),400
    with conn() as c:
        b=c.execute("SELECT * FROM books WHERE id=?",(bid,)).fetchone()
        if not b: return jsonify(error="Book not found."),404
        borrowed=b["total_copies"]-b["available_copies"]
        if copies < borrowed: return jsonify(error=f"Total copies cannot be less than the {borrowed} currently borrowed."),409
        available=copies-borrowed
        c.execute("UPDATE books SET title=?,author=?,category=?,total_copies=?,available_copies=? WHERE id=?",(title,author,category,copies,available,bid))
    return jsonify(message="Book details updated.")

@app.delete("/api/admin/books/<int:bid>")
@admin_required
def delete_book(bid):
    with conn() as c:
        b=c.execute("SELECT id FROM books WHERE id=?",(bid,)).fetchone()
        if not b: return jsonify(error="Book not found."),404
        related=c.execute("SELECT COUNT(*) FROM loans WHERE book_id=?",(bid,)).fetchone()[0]
        if related: return jsonify(error="This book has lending history and cannot be deleted. You can edit its details instead."),409
        c.execute("DELETE FROM books WHERE id=?",(bid,))
    return jsonify(message="Book deleted.")

@app.get("/api/admin/stats")
@admin_required
def admin_stats():
    with conn() as c:
        books=c.execute("SELECT COUNT(*) total_titles,COALESCE(SUM(total_copies),0) total_copies,COALESCE(SUM(available_copies),0) available_copies FROM books").fetchone()
        users_count=c.execute("SELECT COUNT(*) FROM users WHERE role!='admin'").fetchone()[0]
        pending=c.execute("SELECT COUNT(*) FROM loans WHERE status='pending'").fetchone()[0]
        active=c.execute("SELECT COUNT(*) FROM loans WHERE status='approved'").fetchone()[0]
        overdue=c.execute("SELECT COUNT(*) FROM loans WHERE status IN ('approved','return_requested') AND due_at<CURRENT_TIMESTAMP").fetchone()[0]
        reservations=c.execute("SELECT COUNT(*) FROM reservations WHERE status='waiting'").fetchone()[0]
        fine_total=c.execute("SELECT COALESCE(SUM(MAX(0,CAST(julianday('now')-julianday(due_at) AS INTEGER))*5),0) FROM loans WHERE status IN ('approved','return_requested') AND due_at<CURRENT_TIMESTAMP").fetchone()[0]
    return jsonify(stats={**dict(books),"registered_users":users_count,"pending_requests":pending,"active_loans":active,"overdue_loans":overdue,"waiting_reservations":reservations,"estimated_fines":fine_total})


@app.post("/api/reservations")
@login_required
def reserve_book():
    d=request.get_json(silent=True) or {}
    try: bid=int(d.get("book_id"))
    except (TypeError,ValueError): return jsonify(error="A valid book ID is required."),400
    with conn() as c:
        book=c.execute("SELECT id,available_copies FROM books WHERE id=?",(bid,)).fetchone()
        if not book: return jsonify(error="Book not found."),404
        if book['available_copies']>0: return jsonify(error="Copies are available. You can request a loan directly."),409
        active=c.execute("SELECT id FROM loans WHERE user_id=? AND book_id=? AND status IN ('pending','approved','return_requested')",(request.user['id'],bid)).fetchone()
        if active: return jsonify(error="You already have an active request or loan for this book."),409
        waiting=c.execute("SELECT id FROM reservations WHERE user_id=? AND book_id=? AND status='waiting'",(request.user['id'],bid)).fetchone()
        if waiting: return jsonify(error="You are already on the waitlist for this book."),409
        c.execute("INSERT INTO reservations(user_id,book_id,status) VALUES(?,?,'waiting')",(request.user['id'],bid))
    return jsonify(message="You have joined the book waitlist."),201

@app.get("/api/reservations")
@login_required
def my_reservations():
    with conn() as c:
        rows=c.execute("SELECT r.id,r.status,r.created_at,b.title,b.author FROM reservations r JOIN books b ON b.id=r.book_id WHERE r.user_id=? ORDER BY r.created_at DESC",(request.user['id'],)).fetchall()
    return jsonify(reservations=[dict(r) for r in rows])

@app.delete("/api/reservations/<int:rid>")
@login_required
def cancel_reservation(rid):
    with conn() as c:
        cur=c.execute("UPDATE reservations SET status='cancelled' WHERE id=? AND user_id=? AND status='waiting'",(rid,request.user['id']))
        if not cur.rowcount: return jsonify(error="Waiting reservation not found."),404
    return jsonify(message="Reservation cancelled.")

@app.get("/api/announcements")
@login_required
def announcements():
    with conn() as c:
        rows=c.execute("SELECT id,title,message,created_at FROM announcements WHERE active=1 ORDER BY created_at DESC LIMIT 30").fetchall()
    return jsonify(announcements=[dict(r) for r in rows])

@app.post("/api/admin/announcements")
@admin_required
def create_announcement():
    d=request.get_json(silent=True) or {}; title=str(d.get('title','')).strip()[:120]; message=str(d.get('message','')).strip()[:2000]
    if not title or not message: return jsonify(error="Title and message are required."),400
    with conn() as c: c.execute("INSERT INTO announcements(title,message,created_by) VALUES(?,?,?)",(title,message,request.user['id']))
    return jsonify(message="Announcement published to all members."),201

@app.delete("/api/admin/announcements/<int:aid>")
@admin_required
def delete_announcement(aid):
    with conn() as c:
        cur=c.execute("UPDATE announcements SET active=0 WHERE id=? AND active=1",(aid,))
        if not cur.rowcount: return jsonify(error="Announcement not found."),404
    return jsonify(message="Announcement archived.")

@app.get("/api/books/<int:bid>/reviews")
def book_reviews(bid):
    with conn() as c:
        if not c.execute("SELECT id FROM books WHERE id=?",(bid,)).fetchone(): return jsonify(error="Book not found."),404
        rows=c.execute("SELECT r.id,r.rating,r.review,r.created_at,u.name reviewer FROM reviews r JOIN users u ON u.id=r.user_id WHERE r.book_id=? ORDER BY r.created_at DESC",(bid,)).fetchall()
        avg=c.execute("SELECT COALESCE(ROUND(AVG(rating),1),0) rating,COUNT(*) count FROM reviews WHERE book_id=?",(bid,)).fetchone()
    return jsonify(reviews=[dict(r) for r in rows],summary=dict(avg))

@app.post("/api/books/<int:bid>/reviews")
@login_required
def add_review(bid):
    d=request.get_json(silent=True) or {}; review=str(d.get('review','')).strip()[:1000]
    try: rating=int(d.get('rating'))
    except (TypeError,ValueError): return jsonify(error="Rating must be from 1 to 5."),400
    if rating<1 or rating>5: return jsonify(error="Rating must be from 1 to 5."),400
    with conn() as c:
        if not c.execute("SELECT id FROM books WHERE id=?",(bid,)).fetchone(): return jsonify(error="Book not found."),404
        if not c.execute("SELECT id FROM loans WHERE user_id=? AND book_id=? AND status='returned'",(request.user['id'],bid)).fetchone(): return jsonify(error="You can review a book after its return is confirmed."),403
        c.execute("INSERT INTO reviews(user_id,book_id,rating,review) VALUES(?,?,?,?) ON CONFLICT(user_id,book_id) DO UPDATE SET rating=excluded.rating,review=excluded.review,created_at=CURRENT_TIMESTAMP",(request.user['id'],bid,rating,review))
    return jsonify(message="Your review has been saved.")

@app.get("/api/fines")
@login_required
def my_fines():
    with conn() as c:
        rows=c.execute("SELECT l.id,b.title,l.due_at,CAST(julianday('now')-julianday(l.due_at) AS INTEGER) overdue_days,MAX(0,CAST(julianday('now')-julianday(l.due_at) AS INTEGER))*5 amount FROM loans l JOIN books b ON b.id=l.book_id WHERE l.user_id=? AND l.status IN ('approved','return_requested') AND l.due_at<CURRENT_TIMESTAMP ORDER BY l.due_at",(request.user['id'],)).fetchall()
    return jsonify(currency="INR",rate_per_day=5,fines=[dict(r) for r in rows],total=sum(r['amount'] for r in rows))

init_db()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT","5000")))
