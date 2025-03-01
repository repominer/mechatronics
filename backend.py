#!/usr/bin/env python3
# Simple Video Streaming Backend for RC Tank
# Requires: fastapi, uvicorn, opencv-python

import cv2
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="RC Tank Video Server")

# Add CORS middleware to allow connections from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Camera configuration
CAMERA_CONFIG = {
    "width": 640,    # Width of the video feed
    "height": 480,   # Height of the video feed
    "fps": 30,       # Target frames per second
    "device_id": 0,  # Camera device ID (usually 0 for the first camera)
    "flip_method": 0  # 0=no flip, 2=vertical+horizontal
}

# WebSocket connection tracking
active_connections = []

# Initialize camera
camera = None

def init_camera():
    """Initialize the camera with GStreamer pipeline for Jetson"""
    global camera
    
    try:
        # GStreamer pipeline for CSI camera on Jetson
        # Adjust parameters as needed for your specific Jetson module and camera
        gst_pipeline = (
            f"nvarguscamerasrc sensor-id={CAMERA_CONFIG['device_id']} ! "
            f"video/x-raw(memory:NVMM), width={CAMERA_CONFIG['width']}, height={CAMERA_CONFIG['height']}, "
            f"format=NV12, framerate={CAMERA_CONFIG['fps']}/1 ! "
            f"nvvidconv flip-method={CAMERA_CONFIG['flip_method']} ! "
            f"video/x-raw, width={CAMERA_CONFIG['width']}, height={CAMERA_CONFIG['height']}, format=BGRx ! "
            f"videoconvert ! video/x-raw, format=BGR ! appsink"
        )
        
        # Try to open the camera with the GStreamer pipeline
        camera = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
        
        # Check if camera opened successfully
        if not camera.isOpened():
            logger.warning("Failed to open camera with GStreamer pipeline. Trying default capture.")
            # Fallback to standard capture
            camera = cv2.VideoCapture(CAMERA_CONFIG["device_id"])
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_CONFIG["width"])
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_CONFIG["height"])
            camera.set(cv2.CAP_PROP_FPS, CAMERA_CONFIG["fps"])
            
            if not camera.isOpened():
                raise Exception("Could not open camera with any method")
        
        logger.info("Camera initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize camera: {e}")
        return False

def generate_frames():
    """Generate video frames from camera"""
    global camera
    
    # Ensure camera is initialized
    if camera is None or not camera.isOpened():
        if not init_camera():
            # If camera can't be initialized, generate a test pattern
            return generate_test_pattern()
    
    while True:
        success, frame = camera.read()
        
        if not success:
            logger.warning("Failed to read from camera. Reinitializing...")
            # Try to reinitialize the camera
            if camera is not None:
                camera.release()
            
            time.sleep(1)  # Wait a bit before trying again
            if not init_camera():
                # If reinitialization fails, generate a test pattern
                yield from generate_test_pattern()
                continue
                
            success, frame = camera.read()
            if not success:
                # Still failing, fallback to test pattern
                yield from generate_test_pattern()
                continue
        
        # Add timestamp to frame
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            frame,
            timestamp,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2
        )
        
        # Encode frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        
        # Yield in format expected by multipart/x-mixed-replace
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

def generate_test_pattern():
    """Generate a test pattern when camera is not available"""
    logger.info("Generating test pattern")
    
    while True:
        # Create a black image
        frame = cv2.imread("placeholder.jpg") if os.path.exists("placeholder.jpg") else None
        
        if frame is None:
            # Create a black image with test pattern
            frame = cv2.imread("placeholder.jpg") if os.path.exists("placeholder.jpg") else None
            
            if frame is None:
                # Create a black image with test pattern
                frame = cv2.imread("placeholder.jpg") if os.path.exists("placeholder.jpg") else None
                
                if frame is None:
                    # Create a black image with text if no placeholder image exists
                    frame = cv2.imread("placeholder.jpg") if os.path.exists("placeholder.jpg") else None
                    
                    if frame is None:
                        # Create a black image with test pattern
                        frame = cv2.imread("placeholder.jpg") if os.path.exists("placeholder.jpg") else None
                        
                        if frame is None:
                            # Create a black image with text if no placeholder image exists
                            frame = cv2.imread("placeholder.jpg") if os.path.exists("placeholder.jpg") else None
                            
                            if frame is None:
                                # Create a black image with text if no placeholder image exists
                                frame = np.zeros((CAMERA_CONFIG["height"], CAMERA_CONFIG["width"], 3), np.uint8)
                                
                                # Add test pattern elements
                                # Center text
                                cv2.putText(
                                    frame,
                                    "CAMERA NOT AVAILABLE",
                                    (int(CAMERA_CONFIG["width"]/2) - 150, int(CAMERA_CONFIG["height"]/2)),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    1,
                                    (0, 0, 255),
                                    2
                                )
                                
                                # Add timestamp
                                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                                cv2.putText(
                                    frame,
                                    timestamp,
                                    (10, 30),
                                    cv2.FONT_HERSHEY_SIMPLEX,
                                    0.8,
                                    (255, 255, 255),
                                    2
                                )
                                
                                # Add color bars at the bottom
                                height = CAMERA_CONFIG["height"]
                                width = CAMERA_CONFIG["width"]
                                bar_height = height // 5
                                bar_width = width // 6
                                
                                colors = [
                                    (255, 0, 0),    # Blue
                                    (0, 255, 0),    # Green
                                    (0, 0, 255),    # Red
                                    (255, 255, 0),  # Cyan
                                    (0, 255, 255),  # Yellow
                                    (255, 0, 255)   # Magenta
                                ]
                                
                                for i, color in enumerate(colors):
                                    cv2.rectangle(
                                        frame,
                                        (i * bar_width, height - bar_height),
                                        ((i + 1) * bar_width, height),
                                        color,
                                        -1
                                    )
        
        # Encode frame to JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        
        # Yield in format expected by multipart/x-mixed-replace
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        # Simulate frame rate
        time.sleep(1 / CAMERA_CONFIG["fps"])

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for control communication"""
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"Client connected. Active connections: {len(active_connections)}")
    
    try:
        # Send initial status message
        await websocket.send_text("Connected to RC Tank Video Server")
        
        # Process messages (simple echo for now)
        while True:
            data = await websocket.receive_text()
            # Just echo back for now
            await websocket.send_text(f"Received: {data}")
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Remove connection when client disconnects
        if websocket in active_connections:
            active_connections.remove(websocket)
        logger.info(f"Client disconnected. Active connections: {len(active_connections)}")

@app.get("/video", response_class=StreamingResponse)
async def video_feed():
    """Stream MJPEG video feed"""
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with basic info"""
    return """
    <html>
        <head>
            <title>RC Tank Video Server</title>
            <meta http-equiv="refresh" content="0;url=/index.html">
        </head>
        <body>
            <p>Redirecting to control interface...</p>
        </body>
    </html>
    """

# Startup events
@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    # Create static directory if it doesn't exist
    os.makedirs("static", exist_ok=True)
    
    # Initialize camera
    init_camera()
    
    logger.info("Server started")

# Shutdown events
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global camera
    
    logger.info("Server shutting down")
    
    # Release camera
    if camera is not None:
        camera.release()

# Mount static files (for serving the frontend)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# Main entry point
if __name__ == "__main__":
    import numpy as np  # Import here for test pattern generation
    
    # Launch the server
    uvicorn.run(app, host="0.0.0.0", port=8000)