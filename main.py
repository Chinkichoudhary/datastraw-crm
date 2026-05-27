from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import sqlite3
import datetime

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ─── DATABASE ─────────────────────────────────────────
def get_db():
    conn = sqlite3.connect("crm.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            customer_email TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'Open',
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL,
            note_text TEXT NOT NULL,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ─── HELPERS ──────────────────────────────────────────
def generate_ticket_id():
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    conn.close()
    return f"TKT-{str(count + 1).zfill(3)}"

def rows_to_list(rows):
    result = []
    for row in rows:
        result.append({
            "id": row["id"],
            "ticket_id": row["ticket_id"],
            "customer_name": row["customer_name"],
            "customer_email": row["customer_email"],
            "subject": row["subject"],
            "description": row["description"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        })
    return result

# ─── PAGE ROUTES ──────────────────────────────────────
@app.get("/")
async def home(request: Request, status: str = None, search: str = None):
    conn = get_db()
    query = "SELECT * FROM tickets WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (customer_name LIKE ? OR customer_email LIKE ? OR ticket_id LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%"] * 4)
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    tickets = rows_to_list(rows)
    return templates.TemplateResponse(request, "index.html", {
        "tickets": tickets,
        "current_status": status if status else "",
        "search": search if search else ""
    })

@app.get("/create")
async def create_page(request: Request):
    return templates.TemplateResponse(request, "create.html", {})

@app.get("/ticket/{ticket_id}")
async def ticket_page(request: Request, ticket_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    note_rows = conn.execute("SELECT * FROM notes WHERE ticket_id = ? ORDER BY created_at DESC", (ticket_id,)).fetchall()
    conn.close()
    ticket = {
        "ticket_id": row["ticket_id"],
        "customer_name": row["customer_name"],
        "customer_email": row["customer_email"],
        "subject": row["subject"],
        "description": row["description"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }
    notes = []
    for n in note_rows:
        notes.append({
            "note_text": n["note_text"],
            "created_at": n["created_at"]
        })
    return templates.TemplateResponse(request, "ticket.html", {
        "ticket": ticket,
        "notes": notes
    })

# ─── FORM SUBMISSIONS ─────────────────────────────────
@app.post("/api/tickets")
async def create_ticket(
    customer_name: str = Form(...),
    customer_email: str = Form(...),
    subject: str = Form(...),
    description: str = Form(...)
):
    conn = get_db()
    ticket_id = generate_ticket_id()
    now = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    conn.execute(
        "INSERT INTO tickets (ticket_id, customer_name, customer_email, subject, description, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'Open', ?, ?)",
        (ticket_id, customer_name, customer_email, subject, description, now, now)
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/update/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    status: str = Form(...),
    note: str = Form("")
):
    conn = get_db()
    now = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    conn.execute(
        "UPDATE tickets SET status = ?, updated_at = ? WHERE ticket_id = ?",
        (status, now, ticket_id)
    )
    if note.strip():
        conn.execute(
            "INSERT INTO notes (ticket_id, note_text, created_at) VALUES (?, ?, ?)",
            (ticket_id, note, now)
        )
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/ticket/{ticket_id}", status_code=303)

# ─── JSON API ENDPOINTS ───────────────────────────────
@app.get("/api/tickets")
async def api_get_tickets(status: str = None, search: str = None):
    conn = get_db()
    query = "SELECT * FROM tickets WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if search:
        query += " AND (customer_name LIKE ? OR customer_email LIKE ? OR ticket_id LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%"] * 4)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows_to_list(rows)

@app.get("/api/tickets/{ticket_id}")
async def api_get_ticket(ticket_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    note_rows = conn.execute("SELECT * FROM notes WHERE ticket_id = ?", (ticket_id,)).fetchall()
    conn.close()
    if not row:
        return {"error": "Not found"}
    ticket = {
        "ticket_id": row["ticket_id"],
        "customer_name": row["customer_name"],
        "customer_email": row["customer_email"],
        "subject": row["subject"],
        "description": row["description"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "notes": [{"note_text": n["note_text"], "created_at": n["created_at"]} for n in note_rows]
    }
    return ticket