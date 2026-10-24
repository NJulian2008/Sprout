.PHONY: run seed reset test

# Start the development server with hot-reload
run:
	uv run uvicorn app.main:app --reload

# Populate the database with seed data
seed:
	uv run python seed.py

# Drop and recreate all tables, then re-seed
reset:
	uv run python -c "from app.db.session import reset_db; reset_db()"

# Run the test suite
test:
	uv run pytest
