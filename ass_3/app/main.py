from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.routers import ingestion, analysis, interview, voice

app = FastAPI(title="Interview Accelerator")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(ingestion.router)
app.include_router(analysis.router)
app.include_router(interview.router)
app.include_router(voice.router)
app.include_router(voice.tts_router)


@app.get("/interview", response_class=HTMLResponse)
async def interview_page(request: Request):
    return templates.TemplateResponse(request, "interview.html", {})


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {})


@app.get("/health")
async def health():
    return {"status": "ok"}
