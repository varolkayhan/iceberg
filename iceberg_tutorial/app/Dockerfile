# Start with a clean, stable version of Ubuntu
FROM ubuntu:22.04

# Avoid interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies, including Python and pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user to work as (best practice)
RUN useradd --create-home --shell /bin/bash appuser

# Copy the Python requirements file into the container
COPY --chown=appuser:appuser requirements.txt /home/appuser/requirements.txt

# Install the Python packages
RUN pip3 install --no-cache-dir -r /home/appuser/requirements.txt

# Switch to the non-root user
USER appuser

# Set the default working directory
WORKDIR /home/appuser/work

# Start a bash shell when the container runs
CMD ["/bin/bash"]