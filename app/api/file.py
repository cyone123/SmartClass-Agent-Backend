from fastapi import APIRouter, UploadFile, File, Request
from jose import jwt
import time

router = APIRouter()

JWT_SECRET = "Szn90fT3cXjWNS9ZYMN5XsiVEmd1qREM"
ONLYOFFICE_URL = "http://8.155.29.72"

@router.get("/file/config/{file_id}")
async def get_file_config(file_id: str):
    file_url = f"http://8.155.29.72:9090/file/{file_id}"

    config = {
        "document": {
            "fileType": file_id.split(".")[-1],
            "key": str(int(time.time() * 1000)),
            "title": f"{file_id}",
            "url": file_url
        },
        "documentType": get_document_type(file_id),
        "editorConfig": {
            "lang": "zh",
            "mode": "edit",
            "callbackUrl": "http://fbb985d7.natappfree.cc/api/file/callback"
        }
    }

    # token = jwt.encode(config, JWT_SECRET, algorithm="HS256")
    # config["token"] = token
    return config

@router.post("/file/callback")
async def handle_callback(request: Request):
    body = await request.json()
    url = body.get("url")
    key = body.get("key")
    print(str(body))
    return {"error": 0}
    

def get_document_type(file_id: str):
    ext = file_id.split(".")[-1].lower()
    if ext in ["doc", "docx","html"]:
        return "word"
    elif ext in ["xls", "xlsx"]:
        return "cell"
    elif ext in ["ppt", "pptx"]:
        return "slide"
    elif ext in ["pdf"]:
        return "pdf"
    else:
        return ext