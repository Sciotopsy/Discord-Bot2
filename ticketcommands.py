import discord
from discord import app_commands
from discord.ext import commands
from typing import List
import io
from .ticket_views import TicketView

class TicketCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    async def execute_query(self, query: str, parameters: tuple = ()):
        async with self.bot.database.execute(query, parameters) as cursor:
            return await cursor.fetchall()
            
    async def handle_ticket_closure(self, channel, closer, reason, creator_id, log_channel_id, force_close=False):
        """Centralized ticket closing logic for all ticket closure operations."""
        # Generate transcript
        messages = []
        async for message in channel.history(limit=None, oldest_first=True):
            messages.append(f"[{message.created_at}] {message.author}: {message.content}")
        ticket_transcript = "\n".join(messages)

        # Update database
        await self.execute_query(
            """UPDATE tickets 
               SET closed = 1, 
                   closed_at = CURRENT_TIMESTAMP,
                   reason = ?,
                   transcript = ?
               WHERE channel_id = ?""",
            (reason, ticket_transcript, channel.id)
        )

        # Create embeds
        closure_embed = discord.Embed(
            title="Ticket Forcefully Closed" if force_close else "Ticket Closed",
            description=f"Your ticket in **{channel.guild.name}** has been {'forcefully ' if force_close else ''}closed by {closer.mention}\n\n**Reason:** {reason}",
            color=discord.Color.red() if force_close else discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        log_embed = discord.Embed(
            title="Ticket Forcefully Closed" if force_close else "Ticket Closed",
            description=f"**Ticket:** {channel.name}\n**Closed by:** {closer.mention}\n**Reason:** {reason}",
            color=discord.Color.red() if force_close else discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        # Send to log channel
        if log_channel_id:
            log_channel = channel.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=log_embed)
                await log_channel.send(file=discord.File(
                    fp=io.StringIO(ticket_transcript),
                    filename=f"transcript-{channel.name}.txt"
                ))

        # Notify creator
        creator = channel.guild.get_member(creator_id)
        if creator:
            try:
                await creator.send(embed=closure_embed)
                await creator.send(file=discord.File(
                    fp=io.StringIO(ticket_transcript),
                    filename=f"transcript-{channel.name}.txt"
                ))
            except discord.Forbidden:
                pass

        return ticket_transcript

    async def panel_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        panels = await self.execute_query(
            "SELECT panel_name FROM panels WHERE guild_id = ?", 
            (interaction.guild_id,)
        )
        return [
            app_commands.Choice(name=panel[0], value=panel[0])
            for panel in panels if current.lower() in panel[0].lower()
        ][:25]
    
    @app_commands.command(name="send_panel", description="Send a ticket panel in the current channel")
    @app_commands.autocomplete(panel_name=panel_autocomplete)
    async def send_panel(self, interaction: discord.Interaction, panel_name: str):
        await interaction.response.defer(ephemeral=True)

        panel_data = await self.execute_query(
            "SELECT id, panel_name, embed_title, embed_description, embed_color FROM panels WHERE panel_name = ? AND guild_id = ?",
            (panel_name, interaction.guild.id)
        )

        if not panel_data:
            await interaction.followup.send("Panel not found!", ephemeral=True)
            return

        ticket_options = await self.execute_query(
            """SELECT option_name, roles, category_id, embed_title, 
               embed_description, ticket_question 
               FROM ticket_options WHERE panel_id = ?""",
            (panel_data[0][0],)
        )

        if not ticket_options:
            await interaction.followup.send("This panel has no ticket options configured. Please add options first!", ephemeral=True)
            return

        formatted_options = [
            {
                "name": option[0],
                "roles": option[1].split(',') if option[1] else [],
                "category_id": option[2],
                "embed_title": option[3],
                "embed_description": option[4],
                "questions": option[5].split(',') if option[5] else []
            }
            for option in ticket_options
        ]

        embed = discord.Embed(
            title=panel_data[0][2],
            description=panel_data[0][3],
            color=discord.Color.blue()
        )

        view = TicketView(self.bot, formatted_options)
        message = await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("Panel sent successfully!", ephemeral=True)

    @app_commands.command(name="clear_panels", description="Clear ticket panels")
    @app_commands.choices(clear_type=[
        app_commands.Choice(name="Single Panel", value="single"),
        app_commands.Choice(name="All Panels", value="all")
    ])
    async def clear_panels(self, interaction: discord.Interaction, clear_type: str, panel_name: str = None):
        await interaction.response.defer(ephemeral=True)

        if clear_type == "all":
            await self.execute_query(
                "DELETE FROM panels WHERE guild_id = ?",
                (interaction.guild.id,)
            )
            await interaction.followup.send("All panels have been cleared!", ephemeral=True)
        elif panel_name:
            await self.execute_query(
                "DELETE FROM panels WHERE panel_name = ? AND guild_id = ?",
                (panel_name, interaction.guild.id)
            )
            await interaction.followup.send(f"Panel `{panel_name}` has been cleared!", ephemeral=True)
        else:
            await interaction.followup.send("Please provide a panel name to clear.", ephemeral=True)

    @app_commands.command(name="closerequest", description="Request to close a ticket with a reason and optional timer")
    @app_commands.describe(reason="Reason for closing the ticket")
    async def close_request(self, interaction: discord.Interaction, reason: str, hours: int = None):
        await interaction.response.defer()
        
        ticket_data = await self.execute_query(
            "SELECT user_id, log_channel_id FROM tickets WHERE channel_id = ? AND closed = 0",
            (interaction.channel.id,)
        )
        
        if not ticket_data:
            await interaction.followup.send("This command can only be used in active ticket channels!", ephemeral=True)
            return
            
        ticket_creator_id = ticket_data[0][0]
        log_channel_id = ticket_data[0][1]

        view = ConfirmClose(self, ticket_creator_id, reason, log_channel_id, hours)
        embed = discord.Embed(
            title="Ticket Close Request",
            description=f"{interaction.user.mention} has requested to close this ticket.\n\n**Reason:** {reason}",
            color=discord.Color.blue()
        )
        
        user = interaction.guild.get_member(ticket_creator_id)
        if user:
            await interaction.followup.send(f"{user.mention}", embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="closeticket", description="Immediately close a ticket")
    @app_commands.default_permissions(administrator=True)
    async def close_ticket(self, interaction: discord.Interaction, reason: str):
        ticket_data = await self.execute_query(
            "SELECT user_id, log_channel_id FROM tickets WHERE channel_id = ? AND closed = 0",
            (interaction.channel.id,)
        )

        if not ticket_data:
            await interaction.response.send_message("This is not an active ticket channel!", ephemeral=True)
            return

        creator_id, log_channel_id = ticket_data[0]
        
        await self.handle_ticket_closure(
            interaction.channel,
            interaction.user,
            reason,
            creator_id,
            log_channel_id,
            force_close=True
        )

        await interaction.response.send_message("Closing ticket...", ephemeral=True)
        await interaction.channel.delete(reason=f"Ticket force closed by {interaction.user}")

class ConfirmClose(discord.ui.View):
    def __init__(self, cog, creator_id, reason, log_channel_id, hours=None):
        super().__init__(timeout=hours * 3600 if hours else None)
        self.cog = cog
        self.creator_id = creator_id
        self.reason = reason
        self.log_channel_id = log_channel_id

    @discord.ui.button(label="Confirm Close", style=discord.ButtonStyle.primary)
    async def confirm(self, button_interaction: discord.Interaction, button: discord.ui.Button):
        if button_interaction.user.id != self.creator_id:
            await button_interaction.response.send_message("Only the ticket creator can close this ticket!", ephemeral=True)
            return

        await self.cog.handle_ticket_closure(
            button_interaction.channel,
            button_interaction.user,
            self.reason,
            self.creator_id,
            self.log_channel_id
        )
        await button_interaction.channel.delete(reason="Ticket closed by confirmation.")

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCommands(bot))