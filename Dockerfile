FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

# Imposta la cartella di lavoro nel container
WORKDIR /app

# Copia il file delle dipendenze
COPY requirements.txt .

# Copia il file env
COPY .env .

# Installa le dipendenze
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice del bot nella cartella di lavoro
COPY . .

# Comando per avviare il bot
CMD ["python", "bot.py"]