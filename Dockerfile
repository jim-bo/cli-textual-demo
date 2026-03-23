FROM python:3.11-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory
WORKDIR /app

# Copy the project files
COPY . .

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Expose the port Hugging Face Spaces expects (7860)
EXPOSE 7860

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV SAFE_MODE=1

# Run textual-serve via python -m to ensure it is found within the uv environment
CMD ["uv", "run", "textual", "serve", "--host", "0.0.0.0", "--port", "7860", "PYTHONPATH=/app/src uv run python -m cli_textual.app"]
