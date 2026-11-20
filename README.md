# Smart LMS

A small Flask learning management system using SQLite. The existing HTML pages are served by Flask, and student accounts, course enrollments, assignment records, quiz scores, profile details, and chat history are stored in the database.

## Run locally

1. Install Python 3.10 or newer.
2. In this folder run `python -m venv .venv`.
3. Activate it (`.venv\\Scripts\\Activate.ps1` on Windows).
4. Run `pip install -r requirements.txt`.
5. Run `python app.py` and open http://127.0.0.1:5000.
6. Create a student account from the login page.

SQLite is created automatically as `smart_lms.db` beside `app.py`. Set `SECRET_KEY` to a long random value before deployment. To create the first admin, set `ADMIN_USERNAME` and `ADMIN_PASSWORD` as environment variables before the first start. Admin accounts cannot be created through public sign-up.

## Publish with GitHub and Render

1. Create a GitHub repository and push this project folder (`git init`, `git add .`, `git commit`, then add the GitHub remote and push).
2. In Render, choose **New > Blueprint**, connect the repository, and apply `render.yaml`.
3. Render builds with `pip install -r requirements.txt` and starts `gunicorn app:app`. The blueprint mounts a persistent disk at `/var/data` so the SQLite file survives service restarts and deploys.
4. Open the public `onrender.com` URL Render provides and create an account.

The assignment form records the selected filename and submission status in SQLite. This beginner version does not upload/store the actual file contents.
