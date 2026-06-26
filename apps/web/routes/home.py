from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from apps.web.config import TEMPLATES_DIR

router = APIRouter(tags=["home"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/")
def home(request: Request):
    context = {
        "request": request,
        "title": "SisGeS",
    }
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=context,
    )