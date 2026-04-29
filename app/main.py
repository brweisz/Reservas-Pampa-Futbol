import asyncio
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

import bot
from notificacion import enviar_notificacion

load_dotenv()

# --------------- Models ---------------

class LoginRequest(BaseModel):
    documento: str
    password: str
    email: EmailStr

class BookRequest(BaseModel):
    job_id: str
    class_tuple: dict  # {fecha, nivel, sede}

class JobStatus(BaseModel):
    status: str
    last_checked_at: str | None = None

# --------------- Job Registry ---------------

JOB_REGISTRY: dict[str, dict] = {}

TTL_SECONDS = 6 * 3600  # 6 hours

async def janitor_loop():
    """Evict stale jobs every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        now = datetime.now(timezone.utc)
        stale = [
            jid for jid, rec in JOB_REGISTRY.items()
            if (now - rec["created_at"]).total_seconds() > TTL_SECONDS
        ]
        for jid in stale:
            await _cleanup_job(jid)


async def _cleanup_job(job_id: str):
    rec = JOB_REGISTRY.pop(job_id, None)
    if rec is None:
        return
    task = rec.get("task")
    if task and not task.done():
        task.cancel()
    ctx = rec.get("context")
    if ctx:
        try:
            await ctx.close()
        except Exception:
            pass

# --------------- Lifespan ---------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    janitor = asyncio.create_task(janitor_loop())
    yield
    janitor.cancel()
    # Clean up all remaining jobs
    for jid in list(JOB_REGISTRY):
        await _cleanup_job(jid)
    # Close shared browser
    if bot._browser and bot._browser.is_connected():
        await bot._browser.close()

# --------------- App ---------------

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------- Endpoints ---------------

@app.post("/login")
async def login_endpoint(req: LoginRequest):
    try:
        context = await bot.login(req.documento, req.password)
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e))

    classes = await bot.list_classes(context)

    job_id = str(uuid.uuid4())
    JOB_REGISTRY[job_id] = {
        "context": context,
        "email": req.email,
        "chosen_class": None,
        "status": "waiting",
        "last_checked_at": None,
        "task": None,
        "created_at": datetime.now(timezone.utc),
    }

    return {"job_id": job_id, "classes": classes}


@app.post("/book")
async def book_endpoint(req: BookRequest):
    rec = JOB_REGISTRY.get(req.job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found.")
    if rec["status"] != "waiting":
        raise HTTPException(status_code=400, detail=f"Job is already {rec['status']}.")

    rec["chosen_class"] = req.class_tuple
    rec["status"] = "polling"

    async def _run_poll():
        try:
            async def on_success(clase):
                rec["status"] = "booked"
                try:
                    enviar_notificacion(clase, to=rec["email"])
                except Exception:
                    pass
                await _cleanup_job(req.job_id)

            await bot.poll_and_book(
                rec["context"],
                req.class_tuple,
                on_success=on_success,
            )
        except asyncio.CancelledError:
            pass
        except Exception:
            rec["status"] = "failed"
            try:
                enviar_notificacion(
                    rec.get("chosen_class", {}),
                    to=rec["email"],
                )
            except Exception:
                pass
            await _cleanup_job(req.job_id)

    rec["task"] = asyncio.create_task(_run_poll())
    return {"status": "polling"}


@app.get("/status/{job_id}")
async def status_endpoint(job_id: str):
    rec = JOB_REGISTRY.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "status": rec["status"],
        "last_checked_at": rec["last_checked_at"],
    }


@app.delete("/job/{job_id}")
async def cancel_endpoint(job_id: str):
    rec = JOB_REGISTRY.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found.")
    await _cleanup_job(job_id)
    return {"status": "cancelled"}
