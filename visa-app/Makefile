.PHONY: dev dev-frontend dev-backend

dev:
	@echo "Starting frontend and backend..."
	$(MAKE) dev-backend & $(MAKE) dev-frontend

dev-frontend:
	cd frontend && npm run dev

dev-backend:
	cd backend && uvicorn main:app --reload --port 8080
