import discord
from discord.ext import commands
import random
import os
from dotenv import load_dotenv
import json

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True 

bot = commands.Bot(command_prefix='!', intents=intents)

# --- DA MODIFICARE ---
#CANALE_CERCAPARTITE_ID = os.getenv('ID')
id_canale_str = os.getenv('ID')
CANALE_CERCAPARTITE_ID = int(id_canale_str.strip('\'"'))
# ---------------------

# Nome del file dove il bot salverà la memoria degli scontri
FILE_MEMORIA = "storico_match.json"

def carica_memoria():
    """Carica lo storico dei match dal file JSON."""
    if os.path.exists(FILE_MEMORIA):
        with open(FILE_MEMORIA, "r") as f:
            return json.load(f)
    return {}

def salva_memoria(storico):
    """Salva lo storico dei match nel file JSON."""
    with open(FILE_MEMORIA, "w") as f:
        json.dump(storico, f, indent=4)

class GeneraCoppieView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    @discord.ui.button(label="Genera Coppie", style=discord.ButtonStyle.success, custom_id="btn_genera_coppie")
    async def genera_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        thread = interaction.channel

        # 🛡️ CONTROLLO PERMESSI: Verifica se chi ha cliccato è un Amministratore
        if isinstance(interaction.user, discord.Member) and not interaction.user.guild_permissions.administrator:
            # ephemeral=True significa che il messaggio di errore lo vede solo l'utente che ha cliccato
            await interaction.response.send_message("⛔ Solo gli amministratori del server possono generare le coppie!", ephemeral=True)
            return
        
        # 1. Cerca l'ultimo sondaggio inviato nel thread
        messaggio_sondaggio = None
        # Legge gli ultimi 50 messaggi del post cercando quello con il sondaggio
        async for msg in thread.history(limit=50):
            if msg.poll:
                messaggio_sondaggio = msg
                break 
        
        if not messaggio_sondaggio:
            await interaction.response.send_message("Non riesco a trovare nessun sondaggio in questo post.", ephemeral=True)
            return

        utenti_si = []

        # 2. Cerca la risposta "Si" o "Sì" all'interno del sondaggio
        for answer in messaggio_sondaggio.poll.answers:
            testo_risposta = answer.text.strip().lower() if answer.text else ""
            if testo_risposta in ["si", "sì"]:
                async for user in answer.voters():
                    if not user.bot:
                        utenti_si.append(user.mention)
                break 
        
        if not utenti_si:
            await interaction.response.send_message("Nessuno ha ancora votato 'Sì' al sondaggio.", ephemeral=True)
            return
        
        # 🧠 ALGORITMO DI MATCHMAKING INTELLIGENTE
        storico = carica_memoria()
        random.shuffle(utenti_si) # Mischia per casualità
        pool = list(utenti_si)
        coppie_formate = []

        while len(pool) >= 2:
            p1 = pool.pop(0)
            
            # Assicuriamoci che p1 esista nello storico
            if p1 not in storico:
                storico[p1] = []

            avversario_trovato = None
            indice_avversario = -1

            # Cerca un avversario non presente nello storico di p1
            for i, candidato in enumerate(pool):
                if candidato not in storico[p1]:
                    avversario_trovato = candidato
                    indice_avversario = i
                    break
            
            if avversario_trovato is not None:
                # Abbiamo trovato un avversario nuovo! Lo togliamo dal pool.
                p2 = pool.pop(indice_avversario)
            else:
                # p1 ha già sfidato tutti quelli rimasti nel pool.
                # Azzeriamo la sua memoria e prendiamo il primo disponibile!
                storico[p1] = []
                p2 = pool.pop(0)
            
            # Assicuriamoci che p2 esista nello storico
            if p2 not in storico:
                storico[p2] = []

            # Salviamo il match nelle rispettive memorie, EVITANDO I DOPPIONI
            if p2 not in storico[p1]:
                storico[p1].append(p2)
            
            if p1 not in storico[p2]:
                storico[p2].append(p1)

            # Aggiungiamo alla lista testuale usando il formato menzione <@ID>
            coppie_formate.append(f"⚔️ <{p1}> **VS** <{p2}>")

        # Gestione del giocatore dispari
        if len(pool) == 1:
            p_dispari = pool[0]
            coppie_formate.append(f"🛋️ <{p_dispari}> (Senza avversario - Dispari)")

        # Salva la nuova memoria su file
        salva_memoria(storico)

        risposta = "**🏆 Le iscrizioni sono chiuse! Ecco le coppie: 🏆**\n\n" + "\n".join(coppie_formate)
        
        button.disabled = True
        await interaction.message.edit(view=self)
        await interaction.response.send_message(risposta)

@bot.event
async def on_ready():
    print(f'Bot online come {bot.user}!')
    bot.add_view(GeneraCoppieView())

    print("Controllo eventuali sondaggi non gestiti...")
    try:
        # Recupera il canale cercapartite
        canale = bot.get_channel(CANALE_CERCAPARTITE_ID) or await bot.fetch_channel(CANALE_CERCAPARTITE_ID)
        
        if canale and hasattr(canale, 'threads'):
            # Prende tutti i thread (post) attivi e li ordina dal più recente al più vecchio usando l'ID
            threads_attivi = sorted(canale.threads, key=lambda t: t.id, reverse=True)
            
            if threads_attivi:
                ultimo_thread = threads_attivi[0] # Seleziona SOLO l'ultimo post
                
                messaggio_sondaggio = None
                bot_ha_gia_risposto = False

                # Scansiona gli ultimi 50 messaggi di quell'ultimo post
                async for msg in ultimo_thread.history(limit=50):
                    if msg.author == bot.user:
                        bot_ha_gia_risposto = True # Il bot ha già scritto qui dentro
                    
                    if msg.poll and not messaggio_sondaggio:
                        messaggio_sondaggio = msg # Trova il sondaggio
                
                # Se c'è un sondaggio MA il bot non ha mai scritto nel thread (era offline)
                if messaggio_sondaggio and not bot_ha_gia_risposto:
                    print(f"Sondaggio orfano recuperato nel post: {ultimo_thread.name}")
                    await ultimo_thread.send(
                        "👋 Ciao! Ho visto il sondaggio.\nQuando le iscrizioni sono terminate, clicca qui sotto per generare le coppie casuali tra chi ha votato 'Si'.",
                        view=GeneraCoppieView()
                    )
                else:
                    print("L'ultimo post è già stato gestito o non contiene sondaggi.")
    except Exception as e:
        print(f"Errore durante il controllo dei sondaggi: {e}")

@bot.event
async def on_message(message):
    # Evita che il bot risponda a se stesso o ad altri bot
    if message.author.bot:
        return

    # Verifica: il messaggio è in un Thread? E quel thread è nel canale cercapartite?
    if isinstance(message.channel, discord.Thread) and message.channel.parent_id == CANALE_CERCAPARTITE_ID:
        
        # Il bot reagisce SOLO se il messaggio appena inviato contiene effettivamente un sondaggio nativo
        if message.poll:
            await message.channel.send(
                "👋 Ciao! Ho visto il sondaggio.\nQuando le iscrizioni sono terminate, clicca qui sotto per generare le coppie casuali tra chi ha votato 'Si'.",
                view=GeneraCoppieView()
            )

    # Necessario per far funzionare eventuali altri comandi testuali (se deciderai di aggiungerli in futuro)
    await bot.process_commands(message)

# INSERISCI IL TUO TOKEN
token = os.getenv('TOKEN').strip('\'"')
if token:
    bot.run(token)
else:
    print("ERRORE: Token non trovato! Controlla il file docker-compose.yml") 