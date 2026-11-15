# Hugging Face Docker Space for PyroHarmonize.
# The Space holds only this file and README.md. At build time it downloads the
# public GitHub repository, so the Space always shows what is on GitHub.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Spaces run the container as user ID 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HOST=0.0.0.0 \
    PORT=7860
WORKDIR $HOME

# This file changes whenever GitHub main gets a new commit, so a rebuild
# downloads the newest code instead of reusing an old copy.
ADD --chown=user https://api.github.com/repos/Jeeson-Kurian/pyro-harmonize/git/refs/heads/main $HOME/github-version.json
RUN git clone --depth 1 https://github.com/Jeeson-Kurian/pyro-harmonize.git $HOME/app

WORKDIR $HOME/app
RUN pip install --no-cache-dir --user -r requirements.txt

EXPOSE 7860
CMD ["python", "app.py"]
