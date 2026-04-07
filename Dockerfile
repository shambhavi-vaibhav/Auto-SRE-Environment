FROM python:3.11-bookworm

# 1. Create a non-root user for Hugging Face compatibility
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# 2. Install dependencies (ensure ownership is set to 'user')
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy source files with correct ownership
COPY --chown=user server/ server/
COPY --chown=user inference.py .
COPY --chown=user openenv.yaml .
COPY --chown=user README.md .

# 4. HF Spaces expects port 7860
EXPOSE 7860

# 5. Run using uvicorn
CMD ["python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]