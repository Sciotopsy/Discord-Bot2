import discord
from discord import app_commands
from discord.ext import commands
from typing import Dict, List
import json
from .ticket_views import TicketView
import asyncio

class TicketHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.setup_in_progress: Dict[int, dict] = {}

    async def execute_query(self, query: str, parameters: tuple = ()):
        async with self.bot.database.execute(query, parameters) as cursor:
            return await cursor.fetchall()

    async def get_ticket_options(self, guild_id: int):
        return await self.execute_query(
            """SELECT t.id, t.option_name, t.roles, t.category_id, p.embed_title, p.embed_description, p.log_channel_id
               FROM ticket_options t
               JOIN panels p ON t.panel_id = p.id
               WHERE p.guild_id = ?""",
            (guild_id,)
        )

    @app_commands.command(name="setup_ticket_panel", description="Setup a new ticket panel")
    @app_commands.default_permissions(administrator=True)
    async def setup_ticket_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        self.setup_in_progress[interaction.guild_id] = {
            'panel_name': None,
            'embed_title': None,
            'embed_description': None,
            'category_id': None,
            'ticket_options': []
        }
        
        await self.start_panel_setup(interaction)

    async def start_panel_setup(self, interaction: discord.Interaction):
        self.setup_in_progress[interaction.guild_id] = {
            'panel_name': None,
            'embed_title': None,
            'embed_description': None,
            'log_channel_id': None,
            'ticket_options': []
        }

        embed = discord.Embed(
            title="Ticket Panel Setup",
            description="Please enter the panel name:",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            panel_name_msg = await self.bot.wait_for('message', timeout=300.0, check=check)
            self.setup_in_progress[interaction.guild_id]['panel_name'] = panel_name_msg.content
            await self.prompt_embed_title(interaction)
        except TimeoutError:
            await interaction.followup.send("Setup timed out.", ephemeral=True)
            del self.setup_in_progress[interaction.guild_id]

    async def prompt_embed_title(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Ticket Panel Setup",
            description="Enter the title for the ticket panel embed:",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            title_msg = await self.bot.wait_for('message', timeout=300.0, check=check)
            self.setup_in_progress[interaction.guild_id]['embed_title'] = title_msg.content
            await self.prompt_embed_description(interaction)
        except TimeoutError:
            await interaction.followup.send("Setup timed out.", ephemeral=True)
            del self.setup_in_progress[interaction.guild_id]

    async def prompt_embed_description(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Ticket Panel Setup",
            description="Enter the description for the ticket panel embed:",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed)

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            desc_msg = await self.bot.wait_for('message', timeout=300.0, check=check)
            self.setup_in_progress[interaction.guild_id]['embed_description'] = desc_msg.content
            await self.prompt_log_channel(interaction)
        except TimeoutError:
            await interaction.followup.send("Setup timed out.", ephemeral=True)
            del self.setup_in_progress[interaction.guild_id]

    async def prompt_log_channel(self, interaction: discord.Interaction):
        """
        Prompts the user to provide a log channel for ticket logs.
        Ensures that the input is a valid text channel.
        """
        await interaction.followup.send(
            "Please mention the channel where ticket logs should be sent (e.g., #log-channel).",
            ephemeral=True
        )

        def check(m: discord.Message):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            response: discord.Message = await self.bot.wait_for("message", timeout=60.0, check=check)

            if response.channel_mentions:
                log_channel = response.channel_mentions[0]
                if isinstance(log_channel, discord.TextChannel):
                    channel_id = log_channel.id
                    print(f"Storing log channel ID: {channel_id} (Type: {type(channel_id)})")
                    
                    self.setup_in_progress[interaction.guild_id]['log_channel_id'] = channel_id
                    # Remove ephemeral from reply
                    await response.reply(
                        f"Log channel successfully set to {log_channel.mention}! Moving to next step..."
                    )
                    await self.prompt_ticket_option(interaction)
                    return
                else:
                    # Remove ephemeral from reply
                    await response.reply(
                        "The mentioned channel is not a valid text channel. Please try again."
                    )
            else:
                # Remove ephemeral from reply
                await response.reply(
                    "No channel mentioned. Please try again by mentioning a valid text channel (e.g., #log-channel)."
                )
                await self.prompt_log_channel(interaction)

        except asyncio.TimeoutError:
            await interaction.followup.send(
                "Setup timed out. Please use the setup command again to restart the process.",
                ephemeral=True
            )

    async def prompt_ticket_option(self, interaction: discord.Interaction):
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            # Get ticket option name
            embed = discord.Embed(
                title="Ticket Option Setup",
                description="Enter the name for this ticket option:",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            option_name = await self.bot.wait_for('message', timeout=300.0, check=check)

            # Get ticket embed title
            embed = discord.Embed(
                title="Ticket Embed Setup",
                description="Enter the title for the ticket embed:",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            embed_title = await self.bot.wait_for('message', timeout=300.0, check=check)

            # Get ticket embed description
            embed = discord.Embed(
                title="Ticket Embed Setup",
                description="Enter the description for the ticket embed:",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            embed_description = await self.bot.wait_for('message', timeout=300.0, check=check)

            # Handle multiple questions
            questions = []
            while True:
                embed = discord.Embed(
                    title="Ticket Question Setup",
                    description="Enter a question that users will answer when creating a ticket:",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=embed)
                question = await self.bot.wait_for('message', timeout=300.0, check=check)
                questions.append(question.content)

                class QuestionView(discord.ui.View):
                    def __init__(self):
                        super().__init__()
                        self.value = None

                    @discord.ui.button(label="Add Another Question", style=discord.ButtonStyle.primary)
                    async def add_more(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                        await button_interaction.response.defer()
                        self.value = True
                        self.stop()

                    @discord.ui.button(label="Continue Setup", style=discord.ButtonStyle.success)
                    async def finish(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                        await button_interaction.response.defer()
                        self.value = False
                        self.stop()

                view = QuestionView()
                await interaction.followup.send("Would you like to add another question?", view=view)
                await view.wait()

                if not view.value:
                    break

            # Category selection
            categories = interaction.guild.categories
            options = [discord.SelectOption(label=category.name, value=str(category.id)) 
                      for category in categories]

            class CategorySelect(discord.ui.Select):
                def __init__(self):
                    super().__init__(placeholder="Select a category", options=options)

                async def callback(self, select_interaction: discord.Interaction):
                    self.view.selected_category = int(self.values[0])
                    self.view.stop()

            class CategoryView(discord.ui.View):
                def __init__(self):
                    super().__init__()
                    self.selected_category = None
                    self.add_item(CategorySelect())

            view = CategoryView()
            await interaction.followup.send("Select the category for this ticket option:", view=view)
            await view.wait()

            # Role selection
            embed = discord.Embed(
                title="Role Selection",
                description="Mention all roles that should have access to this ticket type (separate with spaces):",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            roles_msg = await self.bot.wait_for('message', timeout=300.0, check=check)
            role_ids = [role.id for role in roles_msg.role_mentions]

            # Store all the new data
            if interaction.guild_id not in self.setup_in_progress:
                self.setup_in_progress[interaction.guild_id] = {'ticket_options': []}

            self.setup_in_progress[interaction.guild_id]['ticket_options'].append({
                'name': option_name.content,
                'category_id': view.selected_category,
                'roles': role_ids,
                'embed_title': embed_title.content,
                'embed_description': embed_description.content,
                'questions': questions
            })

            await self.prompt_continue_setup(interaction)

        except TimeoutError:
            await interaction.followup.send("Setup timed out.", ephemeral=True)
            if interaction.guild_id in self.setup_in_progress:
                del self.setup_in_progress[interaction.guild_id]
                
                
    async def prompt_continue_setup(self, interaction: discord.Interaction):
        class ContinueView(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.value = None

            @discord.ui.button(label="Add Another Option", style=discord.ButtonStyle.primary)
            async def add_more(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                await button_interaction.response.defer()
                self.value = True
                self.stop()

            @discord.ui.button(label="Finish Setup", style=discord.ButtonStyle.success)
            async def finish(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                await button_interaction.response.defer()
                self.value = False
                self.stop()

        view = ContinueView()
        await interaction.followup.send("Would you like to add another ticket option?", view=view)
        await view.wait()

        if view.value:
            await self.prompt_ticket_option(interaction)
        else:
            await self.save_panel_setup(interaction)

    async def save_panel_setup(self, interaction: discord.Interaction):
        setup_data = self.setup_in_progress[interaction.guild_id]
        print(f"Setup data: {setup_data}")

        # Insert the panel data into the database
        await self.bot.database.execute(
            "INSERT INTO panels (guild_id, panel_name, embed_title, embed_description, embed_color, category_id, log_channel_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (interaction.guild_id,
             setup_data['panel_name'],
             setup_data['embed_title'],
             setup_data['embed_description'],
             str(discord.Color.blue().value),
             setup_data.get('category_id'),
             setup_data.get('log_channel_id'))
        )

        # Get the panel ID
        cursor = await self.bot.database.execute(
            "SELECT id, log_channel_id FROM panels WHERE guild_id = ? AND panel_name = ? ORDER BY id DESC LIMIT 1", 
            (interaction.guild_id, setup_data['panel_name'])
        )
        result = await cursor.fetchone()

        if not result:
            await interaction.followup.send("Failed to create panel. Please try again.", ephemeral=True)
            return

        panel_id = result[0]
        print(f"Panel created with ID: {panel_id}")

        # Save ticket options
        for option in setup_data['ticket_options']:
            await self.bot.database.execute(
                "INSERT INTO ticket_options (panel_id, option_name, roles, category_id, embed_title, embed_description, ticket_question) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (panel_id,
                 option['name'],
                 ','.join(map(str, option['roles'])), 
                 option['category_id'],
                 option['embed_title'],
                 option['embed_description'],
                 ','.join(option['questions']))
            )

        await self.bot.database.commit()

        await interaction.followup.send(
            f"Panel '{setup_data['panel_name']}' created successfully with {len(setup_data['ticket_options'])} options!\nUse `/send_panel` to display it in any channel.", 
            ephemeral=True
        )

        del self.setup_in_progress[interaction.guild_id]

    @app_commands.command(name="edit_panel", description="Edit an existing ticket panel")
    @app_commands.default_permissions(administrator=True)
    async def edit_panel(self, interaction: discord.Interaction, panel_name: str):
        await interaction.response.defer(ephemeral=True)
        
        panel_data = await self.execute_query(
            "SELECT * FROM panels WHERE panel_name = ? AND guild_id = ?",
            (panel_name, interaction.guild_id)
        )
        
        if not panel_data:
            await interaction.followup.send("Panel not found!", ephemeral=True)
            return

        class EditView(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.value = None

            @discord.ui.button(label="Edit Title", style=discord.ButtonStyle.primary)
            async def edit_title(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                self.value = "title"
                self.stop()

            @discord.ui.button(label="Edit Description", style=discord.ButtonStyle.primary)
            async def edit_description(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                self.value = "description"
                self.stop()

            @discord.ui.button(label="Edit Category", style=discord.ButtonStyle.primary)
            async def edit_category(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                self.value = "category"
                self.stop()

            @discord.ui.button(label="Edit Options", style=discord.ButtonStyle.primary)
            async def edit_options(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                self.value = "options"
                self.stop()

        view = EditView()
        await interaction.followup.send("What would you like to edit?", view=view)
        await view.wait()

        if view.value:
            await getattr(self, f"edit_panel_{view.value}")(interaction, panel_data[0][0])

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketHandler(bot))