import discord
from discord.ext import commands
import aiosqlite
import os
from dotenv import load_dotenv

async def execute_query(self, query: str, parameters: tuple = ()):
    async with self.bot.database.execute(query, parameters) as cursor:
        return await cursor.fetchall()

async def update_database_schema(database):
    try:
        await database.execute("""
            CREATE TABLE IF NOT EXISTS db_version (
                version INTEGER PRIMARY KEY
            )
        """)
        
        cursor = await database.execute("SELECT version FROM db_version")
        version = await cursor.fetchone()
        
        if not version:
            await database.execute("INSERT INTO db_version VALUES (1)")
            version = (1,)
            
        if version[0] < 2:
            await database.execute("ALTER TABLE tickets ADD COLUMN reason TEXT")
            await database.execute("UPDATE db_version SET version = 2")
            
        if version[0] < 3:
            await database.execute("ALTER TABLE ticket_options ADD COLUMN embed_title TEXT")
            await database.execute("ALTER TABLE ticket_options ADD COLUMN embed_description TEXT")
            await database.execute("ALTER TABLE ticket_options ADD COLUMN ticket_question TEXT")
            await database.execute("UPDATE db_version SET version = 3")
            
        if version[0] < 4:
            # Add log_channel_id to relevant queries
            await database.execute("""
                CREATE TABLE IF NOT EXISTS temp_panels AS 
                SELECT id, panel_name, category_id, log_channel_id, guild_id, 
                       embed_title, embed_description, embed_color 
                FROM panels
            """)
            await database.execute("DROP TABLE panels")
            await database.execute("ALTER TABLE temp_panels RENAME TO panels")
            
            # Ensure log_channel_id is properly indexed
            await database.execute("""
                CREATE INDEX IF NOT EXISTS idx_panels_log_channel 
                ON panels(log_channel_id)
            """)
            
            # Update the join query efficiency
            await database.execute("""
                CREATE INDEX IF NOT EXISTS idx_ticket_options_panel 
                ON ticket_options(panel_id)
            """)
            
            await database.execute("UPDATE db_version SET version = 4")
            await database.commit()
            
        await database.commit()
        
    except Exception as e:
        print(f"Database update: {e}")
        
    except Exception as e:
        print(f"Database update: {e}")

async def database_db():
    """Set up the database."""
    database = await aiosqlite.connect("database.db")

    await database.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_name TEXT,
            user_id INTEGER,
            channel_id INTEGER,
            guild_id INTEGER,
            log_channel_id INTEGER,
            closed BOOLEAN DEFAULT 0,
            transcript TEXT,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP
        )
    """)
    
    await database.execute("""
        CREATE TABLE IF NOT EXISTS panels (
    		id INTEGER PRIMARY KEY AUTOINCREMENT,
    		panel_name TEXT NOT NULL,
    		category_id INTEGER,
    		log_channel_id INTEGER,
    		guild_id INTEGER NOT NULL,
    		embed_title TEXT NOT NULL,
    		embed_description TEXT NOT NULL,
    		embed_color TEXT NOT NULL
        )
    """)

    await database.execute("""
        CREATE TABLE IF NOT EXISTS ticket_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            panel_id INTEGER NOT NULL,
            option_name TEXT NOT NULL,
            roles TEXT,
            category_id INTEGER NOT NULL,
            embed_title TEXT NOT NULL,
            embed_description TEXT NOT NULL,
            ticket_question TEXT,
            FOREIGN KEY (panel_id) REFERENCES panels (id) ON DELETE CASCADE
        )
    """)

    await update_database_schema(database)
    await database.commit()
    return database

# Initialize bot
load_dotenv()
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    bot.database = await database_db()
    await bot.load_extension("cogs.ticketsetup")
    await bot.load_extension("cogs.ticketcommands")
    await bot.tree.sync()
    print("Bot is ready and commands are synced.")

# Run bot
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("Error: DISCORD_BOT_TOKEN environment variable not set.")