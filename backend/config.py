import os


def get_frontend_url():
    if "FRONTEND_URL" in os.environ:
        return os.environ["FRONTEND_URL"]
    return f"http://localhost:{os.environ.get('FRONTEND_PORT', '3000')}"


def get_backend_port():
    return int(os.environ.get("BACKEND_PORT", "8000"))
