import asyncio
import signal
import webbrowser
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import fiftyone as fo
import uvicorn
import logging
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

fps = 2
model = 'clip-vit-base32-torch'

# Initialize FastAPI app
app = FastAPI()

# Static files and templates setup
app.mount("/static", StaticFiles(directory="./static"), name="static")
templates = Jinja2Templates(directory="./templates")

# Cache to store datasets and frames
datasets_cache = {}
frames_cache = {}

@app.on_event("startup")
async def preload_datasets():
    """
    Preload datasets during startup to reduce delays.
    """
    global datasets_cache
    try:
        # Load datasets into cache
        datasets = await asyncio.to_thread(fo.list_datasets)
        datasets_cache = {name: fo.load_dataset(name) for name in datasets}

        # Precompute frames for smaller datasets
        for dataset_name, dataset in datasets_cache.items():
            if dataset_name not in frames_cache:
                frames_cache[dataset_name] = await asyncio.to_thread(dataset.to_frames, sample_frames=True)

        logger.info("Datasets and frames preloaded into cache.")
    except Exception as e:
        logger.error(f"Error loading datasets: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Handle shutdown tasks, canceling all background tasks and stopping FiftyOne services.
    """
    logger.info("Shutting down the application...")

    # Cancel all pending tasks except the current one
    pending_tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in pending_tasks:
        task.cancel()

    # Await cancellation of all tasks
    await asyncio.gather(*pending_tasks, return_exceptions=True)

    # Stop FiftyOne services
    try:
        fo.core.service.stop()
        logger.info("FiftyOne services stopped successfully.")
    except Exception as e:
        logger.error(f"Error stopping FiftyOne services: {e}")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/datasets", response_class=HTMLResponse)
async def list_datasets(request: Request):
    return templates.TemplateResponse("datasets.html", {"request": request, "datasets": datasets_cache})

@app.get("/api/launch_fiftyone/{dataset_name}")
async def launch_fiftyone_endpoint(dataset_name: str):
    if dataset_name not in datasets_cache:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    
    await asyncio.to_thread(launch_fiftyone, dataset_name)
    return {"message": f"Launching FiftyOne app for dataset '{dataset_name}'."}

def launch_fiftyone(dataset_name):
    try:
        # Check if frames are cached or need to be loaded
        frames = frames_cache.get(dataset_name)
        if not frames:
            dataset = datasets_cache[dataset_name]
            frames = dataset.to_frames(sample_frames=True)
            frames_cache[dataset_name] = frames
        
        session = fo.launch_app(frames)
        session.wait()
    except Exception as e:
        logger.error(f"Error launching FiftyOne app: {e}")

@app.post("/create_dataset")
async def create_dataset(dataset_name: str = Form(...), dataset_dir: str = Form(...)):
    if not os.path.exists(dataset_dir):
        raise HTTPException(status_code=400, detail="Directory not found.")
    if fo.dataset_exists(dataset_name):
        fo.load_dataset(dataset_name).delete()
    dataset = fo.Dataset(dataset_name)
    for subdir, _, files in os.walk(dataset_dir):
        for file in files:
            file_path = os.path.join(subdir, file)
            if file.lower().endswith(".mp4"):
                dataset.add_sample(fo.Sample(filepath=file_path))
    dataset.persistent = True
    datasets_cache[dataset_name] = dataset
    return {"message": f"Dataset '{dataset_name}' created successfully!"}

async def main():
    """
    Main application entry point, handling server startup and graceful shutdown.
    """
    config = uvicorn.Config(app, host="0.0.0.0", port=5010, log_level="info")
    server = uvicorn.Server(config)

    # Gracefully handle shutdown signals
    loop = asyncio.get_event_loop()

    # Register signal handlers to stop the server
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(force_shutdown(server)))

    # Open the browser after a short delay
    asyncio.create_task(open_browser())
    await server.serve()

async def force_shutdown(server):
    """
    Forcefully shuts down the server and cancels all tasks.
    """
    logger.info("Forcefully shutting down...")
    await server.shutdown()

    # Cancel all tasks immediately
    pending_tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in pending_tasks:
        task.cancel()
    await asyncio.gather(*pending_tasks, return_exceptions=True)

    logger.info("Shutdown complete.")
    os._exit(0)  # Immediate exit of the application

async def open_browser():
    await asyncio.sleep(1)
    webbrowser.open("http://127.0.0.1:5010", new=2)

if __name__ == "__main__":
    asyncio.run(main())
