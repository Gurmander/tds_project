from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from helper import verify_secret, handle_query

app = FastAPI()


# --- Enable CORS for all origins ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],          # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],          # Allow all headers
)


# health check
@app.get("/health")
def health_check():
    return {"Status": "Running"}

# post endpoint for repo creation
@app.post("/handle_task")
def handle_task(data: dict):
    
    # Validate secret
    if not verify_secret(data.get("secret", "")):
        return Response(
            content='{"Error": "Invalid Secret"}',
            media_type="application/json",
            status_code=status.HTTP_401_UNAUTHORIZED
        )
    
    else:
        # process the task
        handle_query(data)

        # OK response
        return Response(
            content='{"Data": "Received"}',
            media_type="application/json",
            status_code=status.HTTP_200_OK
        )        





if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)