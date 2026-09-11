import uvicorn

if __name__ == "__main__":
    print("=========================================================")
    print("   Starting Elder Care Production Backend API           ")
    print("   Swagger Docs: http://127.0.0.1:8000/docs              ")
    print("   Health Check: http://127.0.0.1:8000/api/v1/health     ")
    print("=========================================================")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
