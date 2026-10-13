import importlib
import pytest

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKNEST_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("ADMIN_EMAIL", "admin@test.local")
    monkeypatch.setenv("ADMIN_PASSWORD", "TestAdmin123!")
    import app as module
    importlib.reload(module)
    module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with module.app.test_client() as c:
        yield c

def test_health(client):
    r=client.get("/health")
    assert r.status_code==200 and r.get_json()["status"]=="ok"

def test_register_and_catalogue(client):
    r=client.post("/api/register",json={"name":"Test Student","email":"student@test.local","password":"Student123!"})
    assert r.status_code==201
    assert len(client.get("/api/books").get_json()["books"])>=1

def test_admin_can_add_book(client):
    client.post("/api/login",json={"email":"admin@test.local","password":"TestAdmin123!"})
    r=client.post("/api/admin/books",json={"title":"Testing Book","author":"A Tester","category":"Testing","copies":2})
    assert r.status_code==201
    assert any(b["title"]=="Testing Book" for b in client.get("/api/books").get_json()["books"])

def test_admin_api_rejects_student(client):
    client.post("/api/register",json={"name":"Student","email":"s@test.local","password":"Student123!"})
    assert client.get("/api/admin/loans").status_code==403


def test_user_cannot_manage_books(client):
    client.post("/api/register",json={"name":"Regular User","email":"regular@test.local","password":"UserPass123!"})
    r=client.post("/api/admin/books",json={"title":"Not allowed","author":"Test","copies":1})
    assert r.status_code==403


def test_admin_stats_and_book_update(client):
    client.post("/api/login",json={"email":"admin@test.local","password":"TestAdmin123!"})
    book=client.post("/api/admin/books",json={"title":"Editable Book","author":"Author","category":"Testing","copies":2})
    assert book.status_code==201
    found=next(b for b in client.get("/api/books").get_json()["books"] if b["title"]=="Editable Book")
    updated=client.put(f"/api/admin/books/{found['id']}",json={"title":"Edited Book","author":"New Author","category":"Reference","copies":3})
    assert updated.status_code==200
    assert any(b["title"]=="Edited Book" for b in client.get("/api/books").get_json()["books"])
    stats=client.get("/api/admin/stats")
    assert stats.status_code==200 and "overdue_loans" in stats.get_json()["stats"]

def test_admin_can_publish_announcement_and_student_can_read(client):
    client.post('/api/login', json={'email':'admin@test.local','password':'TestAdmin123!'})
    r=client.post('/api/admin/announcements',json={'title':'Holiday hours','message':'Closed on Sunday'})
    assert r.status_code==201
    client.post('/api/logout',json={})
    client.post('/api/register',json={'name':'Member','email':'member@test.local','password':'MemberPass123!'})
    data=client.get('/api/announcements').get_json()['announcements']
    assert data and data[0]['title']=='Holiday hours'

def test_admin_only_can_publish_announcement(client):
    client.post('/api/register',json={'name':'Member','email':'member@test.local','password':'MemberPass123!'})
    assert client.post('/api/admin/announcements',json={'title':'No','message':'No'}).status_code==403

def test_waitlist_only_when_unavailable(client):
    client.post('/api/register',json={'name':'Member','email':'member@test.local','password':'MemberPass123!'})
    book=client.get('/api/books').get_json()['books'][0]
    assert client.post('/api/reservations',json={'book_id':book['id']}).status_code==409
