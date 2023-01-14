.PHONY: fmt
fmt:
	poetry run python -m isort .
	poetry run python -m black .