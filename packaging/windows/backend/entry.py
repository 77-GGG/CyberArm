import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("cyberarm.server:app", host="127.0.0.1", port=int(os.environ.get("CYBERARM_PORT", "8765")))
