"""Run separately: python -m uvicorn export_potential.app:app --port 8001."""
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from .routes import mount
app = FastAPI(title='Silk Export Potential',docs_url=None,redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=['http://127.0.0.1:8001','http://localhost:8001'],allow_methods=['GET'])
mount(app)
app.mount('/fonts',StaticFiles(directory=Path(__file__).resolve().parent.parent/'web/fonts'),name='fonts')
@app.get('/',include_in_schema=False)
def root():
    return RedirectResponse('/export-potential')
