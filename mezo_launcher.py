import multiprocessing
import sys
import os
import uvicorn
import time

def run_control_plane():
    # Setup path and working directory for control plane
    base = os.path.dirname(os.path.abspath(__file__))
    cp_path = os.path.join(base, "mezo-control-plane")
    sys.path.insert(0, cp_path)
    os.chdir(cp_path)
    print("[MEZO LAUNCHER] Starting Control Plane on port 8080...")
    # Passing app as string so uvicorn imports it after path change
    uvicorn.run("main:app", host="0.0.0.0", port=8080, log_level="warning")

def run_ai_engine():
    # Setup path and working directory for ai engine
    base = os.path.dirname(os.path.abspath(__file__))
    engine_path = os.path.join(base, "mezo-ai-engine")
    sys.path.insert(0, engine_path)
    os.chdir(engine_path)
    print("[MEZO LAUNCHER] Starting AI Engine on port 8081...")
    uvicorn.run("main:app", host="0.0.0.0", port=8081, log_level="warning")

def run_security():
    base = os.path.dirname(os.path.abspath(__file__))
    sec_path = os.path.join(base, "mezo-security")
    if os.path.exists(os.path.join(sec_path, "main.py")):
        sys.path.insert(0, sec_path)
        os.chdir(sec_path)
        print("[MEZO LAUNCHER] Starting Security Service on port 8082...")
        uvicorn.run("main:app", host="0.0.0.0", port=8082, log_level="warning")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    print("=======================================")
    print("      MEZO AI BACKEND LAUNCHER")
    print("=======================================")
    
    processes = []
    
    p1 = multiprocessing.Process(target=run_control_plane)
    processes.append(p1)
    
    p2 = multiprocessing.Process(target=run_ai_engine)
    processes.append(p2)
    
    # Check if security has a main.py to run, otherwise skip
    sec_main = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mezo-security", "main.py")
    if os.path.exists(sec_main):
        p3 = multiprocessing.Process(target=run_security)
        processes.append(p3)

    try:
        for p in processes:
            p.start()
        
        # Keep main process alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MEZO LAUNCHER] Shutting down services...")
        for p in processes:
            p.terminate()
            p.join()
        print("[MEZO LAUNCHER] Shutdown complete.")
