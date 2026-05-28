import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
import os
from dotenv import load_dotenv
import json
import asyncio
import networkx as nx
import itertools
from playwright.async_api import async_playwright

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True 

bot = commands.Bot(command_prefix='!', intents=intents)

id_canale_str = os.getenv('ID')
CANALE_CERCAPARTITE_ID = int(id_canale_str.strip('\'"'))
news_id_str = os.getenv('NEWS')
CHANNEL_ID = int(news_id_str.strip('\'"'))
URL_WARCOM = "https://www.warhammer-community.com/en-gb/setting/kill-team/"

memoria_lock = asyncio.Lock()

FILE_MEMORIA = "storico_match.json"
FILE_STATO = "stato_killteam.json"


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
        self.sta_generando = False

    @discord.ui.button(label="Genera Coppie", style=discord.ButtonStyle.success, custom_id="btn_genera_coppie")
    async def genera_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        thread = interaction.channel

        if self.sta_generando:
            return
        
        self.sta_generando = True

        if isinstance(interaction.user, discord.Member) and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⛔ Solo gli amministratori del server possono generare le coppie!", ephemeral=True)
            self.sta_generando = False
            return
        
        await interaction.response.defer()

        button.disabled = True
        await interaction.message.edit(view=self)

        messaggio_sondaggio = None
        async for msg in thread.history(limit=50):
            if msg.poll:
                messaggio_sondaggio = msg
                break 
        
        if not messaggio_sondaggio:
            self.sta_generando = False
            button.disabled = False
            await interaction.message.edit(view=self)
            await interaction.followup.send("Non riesco a trovare nessun sondaggio in questo post.", ephemeral=True) 
            return

        utenti_si = []
        trovato_si = False

        for answer in messaggio_sondaggio.poll.answers:
            testo_risposta = answer.text.strip().lower() if answer.text else ""
            if testo_risposta in ["si", "sì"]:
                trovato_si = True
                async for user in answer.voters():
                    if not user.bot:
                        utenti_si.append(user.mention)
                break
        
        if not trovato_si:
            self.sta_generando = False
            button.disabled = False
            await interaction.message.edit(view=self)
            await interaction.followup.send("Per favore, rifai il sondaggio mettendo 'si' come opzione di risposta.", ephemeral=True)
            return
        
        if not utenti_si:
            self.sta_generando = False
            button.disabled = False
            await interaction.message.edit(view=self)
            await interaction.followup.send("Nessuno ha ancora votato 'Sì' al sondaggio.", ephemeral=True)
            return
        
        if len(utenti_si) < 2:
            self.sta_generando = False
            button.disabled = False
            await interaction.message.edit(view=self)
            await interaction.followup.send("❌ Servono almeno 2 partecipanti per generare i match!", ephemeral=True)
            return
        
        async with memoria_lock:
            storico = carica_memoria()
            
            G = nx.Graph()
            G.add_nodes_from(utenti_si)

            base_dinamica = len(utenti_si) + 1
            
            for p1, p2 in itertools.combinations(utenti_si, 2):
                volte_giocate = storico.get(p1, []).count(p2)
                peso_totale = (base_dinamica ** volte_giocate) * 1000 + random.randint(0, 500)
                G.add_edge(p1, p2, weight=peso_totale)
            
            matchup_ottimali = nx.min_weight_matching(G, weight='weight')
            
            giocatori_matchati = set(itertools.chain.from_iterable(matchup_ottimali))
            giocatori_in_panchina = list(set(utenti_si) - giocatori_matchati)
            
            coppie_formate = []
            numero_coppie = 0

            for p1, p2 in matchup_ottimali:
                volte_giocate = storico.get(p1, []).count(p2)
                
                if p1 not in storico:
                    storico[p1] = []
                if p2 not in storico:
                    storico[p2] = []

                storico[p1].append(p2)
                storico[p2].append(p1)

                numero_coppie += 1
                coppie_formate.append(f"⚔️ {p1} **VS** {p2}")

            if giocatori_in_panchina:
                p_dispari = giocatori_in_panchina[0]
                coppie_formate.append(f"🛋️ {p_dispari} (Senza avversario - Dispari)")

            salva_memoria(storico)

        risposta = "**🏆 Le iscrizioni sono chiuse! Ecco le coppie: 🏆**\n\n" + "\n".join(coppie_formate)

        campi = ["Volkus","Mondo Tomba"]
        message = []

        for i in range(numero_coppie):
            campo_scelto = random.choice(campi)
            random_number = random.randint(1, 6)
            message.append(f"⚔️ **Campo per la coppia {i+1}: {campo_scelto}** (Numero: **{random_number}**)")

        risposta += "\n\n**Ecco i campi per le coppie:**\n\n" + "\n".join(message)
        
        await interaction.followup.send(risposta)


async def get_latest_news():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(URL_WARCOM, wait_until="networkidle")
            section = page.locator('section', has=page.locator('h2', has_text="All Kill Team News"))
            list_container = section.locator('ul.row.flex')
            await list_container.wait_for(state="visible", timeout=15000)
            
            first_li = list_container.locator('li').first
            await first_li.wait_for(state="visible", timeout=10000)
            
            news_data = await first_li.evaluate('''(li) => {
                const aTag = li.querySelector('a[href]');
                const href = aTag ? aTag.getAttribute('href') : '';
                
                const titleTag = li.querySelector('h3, h4, h5, [class*="heading"], [class*="title"]');
                const title = titleTag ? titleTag.innerText.trim() : 'Titolo non trovato';
                
                let dateText = "Data sconosciuta";
                const timeTag = li.querySelector('time');
                if (timeTag) {
                    dateText = timeTag.innerText.trim();
                } else {
                    const match = li.innerText.match(/\\d{2}\\s+[A-Za-z]{3}\\s+\\d{2}/);
                    if (match) {
                        dateText = match[0];
                    }
                }
                
                return { title: title, href: href, date: dateText };
            }''')
            
            link = news_data['href']
            if link and not link.startswith("http"):
                link = f"https://www.warhammer-community.com{link}"
            elif not link:
                link = "Link non trovato"
                
            return {"title": news_data['title'], "link": link, "date": news_data['date']}
            
        except Exception as e:
            print(f"Errore Playwright: {e}")
            return None
        finally:
            await browser.close()


@tasks.loop(minutes=60) # Controlla ogni ora (puoi modificare l'intervallo)
async def warcom_news_loop():
    print("Controllo nuove notizie Kill Team in background...")
    latest_news = await get_latest_news()
    
    if not latest_news or latest_news['link'] == "Link non trovato":
        return

    # Gestione file di stato locale
    if os.path.exists(FILE_STATO):
        with open(FILE_STATO, 'r') as f:
            stato = json.load(f)
    else:
        stato = {"ultimo_link": ""}

    # Se la notizia è nuova, inviala al canale
    if latest_news['link'] != stato['ultimo_link']:
        channel = bot.get_channel(CHANNEL_ID)
        
        if channel:
            messaggio = f"🚨 **Nuova notizia Kill Team!** 🚨\n**{latest_news['title']}** - {latest_news['date']}\n{latest_news['link']}"
            await channel.send(messaggio)
            print("Notizia inviata nel canale Discord!")
            
            # Aggiorna il JSON solo se l'invio ha successo
            stato['ultimo_link'] = latest_news['link']
            with open(FILE_STATO, 'w') as f:
                json.dump(stato, f)
        else:
            print(f"Errore: Impossibile trovare il canale con ID {CHANNEL_ID}")
    else:
        print("Nessuna nuova notizia.")


@warcom_news_loop.before_loop
async def before_warcom_news_loop():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    bot.add_view(GeneraCoppieView())

    if not warcom_news_loop.is_running():
        warcom_news_loop.start()

    # --- SINCRONIZZA I COMANDI SLASH ---
    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"Errore nella sincronizzazione dei comandi slash: {e}")

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


@bot.tree.command(name="add", description="Aggiunge manualmente una coppia")
@app_commands.describe(
    giocatore1="Seleziona il primo giocatore",
    giocatore2="Seleziona il secondo giocatore"
)
# Questa riga nasconde il comando a chi non è amministratore!
@app_commands.default_permissions(administrator=True) 
async def add_match(interaction: discord.Interaction, giocatore1: discord.Member, giocatore2: discord.Member):
    
    # Controllo di sicurezza: evitare che uno sfidi se stesso
    if giocatore1.mention == giocatore2.mention:
        await interaction.response.send_message("⛔ Non puoi far scontrare un giocatore contro se stesso!", ephemeral=True)
        return

    # Trasformiamo subito gli oggetti Member in ID testuali per il JSON
    id1 = str(giocatore1.mention)
    id2 = str(giocatore2.mention)

    # Apriamo il file in sicurezza con il lucchetto
    async with memoria_lock:
        storico = carica_memoria()

        # Ci assicuriamo che entrambi i giocatori esistano nel dizionario
        if id1 not in storico:
            storico[id1] = []
        if id2 not in storico:
            storico[id2] = []

        # Aggiungiamo i rispettivi ID incrociati (evitando doppioni)
        if id2 not in storico[id1]:
            storico[id1].append(id2)
        if id1 not in storico[id2]:
            storico[id2].append(id1)

        salva_memoria(storico)

    # Diamo conferma visiva dell'avvenuta operazione
    await interaction.response.send_message(f"✅ **Match registrato!**\n{giocatore1.mention} vs {giocatore2.mention}")


@bot.tree.command(name="remove", description="Rimuove manualmente una coppia")
@app_commands.describe(
    giocatore1="Seleziona il primo giocatore",
    giocatore2="Seleziona il secondo giocatore"
)
@app_commands.default_permissions(administrator=True)
async def remove_match(interaction: discord.Interaction, giocatore1: discord.Member, giocatore2: discord.Member):
    
    if giocatore1.mention == giocatore2.mention:
        await interaction.response.send_message("⛔ Non puoi rimuovere un match contro se stesso!", ephemeral=True)
        return
    
    id1 = str(giocatore1.mention)
    id2 = str(giocatore2.mention)

    async with memoria_lock:
        storico = carica_memoria()

        match_rimosso = False

        # 3. PREVENZIONE KEYERROR: Controlliamo PRIMA se id1 esiste nel dizionario
        if id1 in storico and id2 in storico[id1]:
            storico[id1].remove(id2)
            match_rimosso = True
            
        # Facciamo lo stesso controllo incrociato per id2
        if id2 in storico and id1 in storico[id2]:
            storico[id2].remove(id1)
            match_rimosso = True

        # Se abbiamo modificato qualcosa, salviamo il file
        if match_rimosso:
            salva_memoria(storico)
            await interaction.response.send_message(f"✅ **Match rimosso con successo!**\nCancellato lo scontro tra {giocatore1.mention} e {giocatore2.mention}.")
        else:
            # Se non c'era nessun match salvato tra i due
            await interaction.response.send_message(f"⚠️ **Nessun match trovato!**\n{giocatore1.mention} e {giocatore2.mention} non si erano mai sfidati.")


@bot.tree.command(name="replace", description="Cambia due coppie")
@app_commands.describe(
    giocatore1="Seleziona il primo giocatore contro il secondo",
    giocatore2="Seleziona il secondo giocatore contro il primo",
    giocatore3="Seleziona il terzo giocatore contro il quarto",
    giocatore4="Seleziona il quarto giocatore contro il terzo"
)
@app_commands.default_permissions(administrator=True)
async def replace_match(interaction: discord.Interaction, giocatore1: discord.Member, giocatore2: discord.Member, giocatore3: discord.Member, giocatore4: discord.Member):
    
    if giocatore1.mention == giocatore2.mention or giocatore3.mention == giocatore4.mention:
        await interaction.response.send_message("⛔ Non puoi selezionare lo stesso giocatore due volte!", ephemeral=True)
        return
    
    id1 = str(giocatore1.mention)
    id2 = str(giocatore2.mention)
    id3 = str(giocatore3.mention)
    id4 = str(giocatore4.mention)
    #TODO: prende il match tra id1 e id2, lo rimuove, prende il match tra id3 e id4, lo rimuove, poi crea i nuovi match id1 vs id3 e id2 vs id4 (con tutti i controlli del caso)

    async with memoria_lock:
        storico = carica_memoria()

        # Rimuoviamo i vecchi match (con i controlli di sicurezza)
        if id1 in storico and id2 in storico[id1]:
            storico[id1].remove(id2)
        if id2 in storico and id1 in storico[id2]:
            storico[id2].remove(id1)
        if id3 in storico and id4 in storico[id3]:
            storico[id3].remove(id4)
        if id4 in storico and id3 in storico[id4]:
            storico[id4].remove(id3)

        # Aggiungiamo i nuovi match
        if id3 not in storico:
            storico[id3] = []
        if id4 not in storico:
            storico[id4] = []
        if id1 not in storico:
            storico[id1] = []
        if id2 not in storico:
            storico[id2] = []

        if id3 not in storico[id1]:
            storico[id1].append(id3)
        if id1 not in storico[id3]:
            storico[id3].append(id1)
        
        if id4 not in storico[id2]:
            storico[id2].append(id4)
        if id2 not in storico[id4]:
            storico[id4].append(id2)

        salva_memoria(storico)

        await interaction.response.send_message(f"✅ **Match sostituiti con successo!**\n{giocatore1.mention} ora sfida {giocatore3.mention}\n{giocatore2.mention} ora sfida {giocatore4.mention}")


@bot.tree.command(name="campi", description="Crea i campi e il loro numero")
@app_commands.describe(
    numero_coppie="Seleziona il numero di coppie partecipanti",
)
@app_commands.default_permissions(administrator=True)
async def campi_random(interaction: discord.Interaction, numero_coppie: int):

    campi = ["Volkus","Mondo Tomba"]
    message = []

    for i in range(numero_coppie):
        campo_scelto = random.choice(campi)
        random_number = random.randint(1, 6)
        message.append(f"⚔️ **Campo per la coppia {i+1}: {campo_scelto}** (Numero: {random_number})")
    await interaction.response.send_message("Ecco i campi per le coppie:\n" + "\n".join(message))


# INSERISCI IL TUO TOKEN
token = os.getenv('TOKEN').strip('\'"')
if token:
    bot.run(token)
else:
    print("ERRORE: Token non trovato! Controlla il file docker-compose.yml") 