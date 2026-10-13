# BookNest: Containerized Library Management with Automated CI/CD

BookNest is a DevOps laboratory mini project using Flask, SQLite, Docker, Git/GitHub, Jenkins, Pytest, and Ansible.

## Features
- Student registration and login with hashed passwords.
- Searchable book catalogue and available-copy counts.
- Borrow requests; admin approval or rejection.
- Student return request; admin return confirmation.
- Separate welcome, login, signup, and dashboard pages.
- Role-based access: registered accounts are regular users; only the seeded administrator can manage inventory, approve/reject requests, confirm returns, and view all users.
- Student/user lending history, with a 14-day due date and overdue indicators.
- Admin overview cards for titles, total/available copies, registered users, pending requests, active loans, and overdue loans.
- Admin inventory management: add/edit books; deletion is blocked when a book has lending history.
- **Waitlist / reservations:** users can join a waitlist for currently unavailable titles and cancel their waiting reservation.
- **Library announcements:** admins publish notices for all authenticated members; admins can archive outdated notices.
- **Ratings and reviews:** members can rate and review books only after the return is confirmed; catalogue shows average rating and review count.
- **Overdue fine estimator:** approval sets the due date to 14 days from approval. After the due date, the demo estimates ₹5 per overdue calendar day (for example, 3 overdue days = ₹15). The estimate continues while a return request is awaiting admin confirmation and stops when the return is confirmed. It is recalculated from the current date when the fines view is loaded; it is not a payment gateway or an official fine ledger.
- Admin dashboard includes waiting reservation count and estimated overdue charges.
- SQLite data persisted in the local `./data` folder via Docker Compose.
- Pytest tests, GitHub Actions CI, and Jenkins pipeline with Ansible deployment.

## Requirements
Python 3.11+, Git, Docker Desktop or Docker Engine with Docker Compose, and (for the full pipeline) Jenkins, Ansible, and Docker access for the Jenkins agent.

## Run locally
```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000.

Admin access: open the same `/login` page used by members and sign in with the local demo credentials `admin@booknest.local` / `Admin123!`. The dashboard detects the administrator role and displays Inventory, Members, and Loan requests. These credentials are for local demonstration only. Change them before deployment and use a strong `SECRET_KEY`. New signups are always regular users; do not add a public role selector, because users must not be able to register themselves as administrators.

## Updating an existing Docker run
After replacing the application files, rebuild and restart with `docker compose up --build -d`. The database is stored under `./data`; keep that folder to preserve accounts, books, and lending history. Do not delete it when updating the app.

## Run with Docker Compose
1. Copy `.env.example` to `.env` and edit the values.
2. Run:
```bash
docker compose up --build -d
docker compose ps
docker compose logs -f
```
Open http://localhost:5000. Stop using `docker compose down`. The database volume persists. `docker compose down -v` deletes it.

## Tests
```bash
pip install -r requirements.txt
pytest -q
```

## Jenkins + Ansible
Configure a Jenkins Pipeline job for this Git repository and select `Jenkinsfile`. The Jenkins agent needs Python 3, Docker CLI access to the Docker daemon, Ansible, and the Docker collection:
```bash
python3 -m pip install ansible
ansible-galaxy collection install community.docker
```
The included inventory deploys to `localhost` on the Jenkins agent. To deploy to a separate machine, update `ansible/inventory.ini` and configure SSH credentials securely in Jenkins. Configure `SECRET_KEY`, `ADMIN_EMAIL`, and `ADMIN_PASSWORD` in Jenkins environment/credentials; never commit real secrets.

## Git workflow evidence
Create meaningful branches and commits. Example:
```bash
git init
git add .
git commit -m "chore: initialize BookNest project"
git branch -M main
git switch -c feature/student-auth
# Make a small improvement, then:
git add .
git commit -m "feat: implement student authentication"
git switch main
git merge feature/student-auth
git switch -c feature/loan-workflow
# Make another improvement and commit it, then:
git switch main
git merge feature/loan-workflow
```
Create an empty GitHub repository named `BookNest`, then:
```bash
git remote add origin https://github.com/YOUR-USERNAME/BookNest.git
git push -u origin main
git push origin feature/student-auth feature/loan-workflow
```
Replace `YOUR-USERNAME` with your username. Demonstrate merge conflict handling only by creating and resolving a real conflict in a test branch or collaboration workflow.

## CI workflow
`.github/workflows/ci.yml` runs tests and builds a Docker image on pushes to `main`/`develop` and pull requests to `main`.

## Architecture
```text
Browser -> index.html (HTML/CSS/JavaScript) -> Flask API (app.py) -> SQLite
GitHub -> Jenkins -> Pytest -> Docker build -> Ansible -> running container
```

## API endpoints
- `POST /api/register`, `POST /api/login`, `POST /api/logout`
- `GET /api/books`, `POST /api/loans`, `GET /api/history`
- `POST /api/loans/<id>/return`
- User: `POST /api/reservations`, `GET /api/reservations`, `DELETE /api/reservations/<id>`, `GET /api/fines`, `POST /api/books/<id>/reviews`, `GET /api/books/<id>/reviews`, `GET /api/announcements`
- Admin: `POST /api/admin/books`, `GET /api/admin/loans`, `POST /api/admin/loans/<id>/decision`, `POST /api/admin/loans/<id>/confirm-return`, `GET /api/admin/users`, `POST /api/admin/announcements`, `DELETE /api/admin/announcements/<id>`
- `GET /health`

## Scope note
This is a lab/demo starter, not a production system. It does not yet include email/SMS notifications, online fine payments, password reset, CSRF protection, rate limiting, or production secret management. The waitlist, ratings, notices, and fine estimator are local demo features; test them before presenting the app as production-ready.


## Separate authentication pages

- `/` — welcome page with separate Login and Create account links
- `/login` — login page
- `/signup` — student registration page
- `/dashboard` — authenticated library dashboard

## Keep BookNest database data on the project drive

Docker Compose maps `./data` on the host to `/app/data` in the container. If your project is extracted to `D:\BookNest`, SQLite data is stored in `D:\BookNest\data\booknest.db`. Create the `data` folder if it does not exist.

Docker Desktop itself may still store its Linux engine image on C:. To move Docker's own disk image, open Docker Desktop → Settings → Resources → Advanced → Disk image location, choose a folder on D: (for example `D:\DockerData`), and apply/restart. The option may differ by Docker Desktop version. Ensure D: has enough free space and do not manually delete Docker's existing disk image.

From PowerShell in the BookNest folder:
```powershell
docker compose up --build -d
docker compose ps
```
