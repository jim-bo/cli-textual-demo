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

# Run textual-serve; use SPACE_HOST (set by HF Spaces) for public URL so
# the served HTML references the correct host instead of 0.0.0.0.
CMD ["sh", "-c", "uv run textual serve --host 0.0.0.0 --port 7860 ${SPACE_HOST:+--url https://$SPACE_HOST} 'PYTHONPATH=/app/src uv run python -m cli_textual.app'"]
