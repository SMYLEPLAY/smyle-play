web: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2 --access-log
release: cd smyleplay-api && alembic upgrade head
