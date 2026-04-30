import sys
print("Python version:", sys.version)
try:
    import fastapi
    print("FastAPI imported")
    import uvicorn
    print("Uvicorn imported")
    import sqlalchemy
    print("SQLAlchemy imported")
except ImportError as e:
    print("Import error:", e)
