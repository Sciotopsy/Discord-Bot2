import discord

class TicketModal(discord.ui.Modal):
    def __init__(self, questions: list, ticket_data: dict):
        super().__init__(title="Ticket Creation", timeout=None)
        self.ticket_data = ticket_data
        self.responses = []
        
        for i, question in enumerate(questions):
            truncated_question = question[:45] if len(question) > 45 else question
            text_input = discord.ui.TextInput(
                label=truncated_question,
                style=discord.TextStyle.paragraph,
                max_length=1000,
                required=True
            )
            self.add_item(text_input)
            self.responses.append(text_input)

class TicketView(discord.ui.View):
    def __init__(self, bot, options):
        super().__init__(timeout=None)
        self.bot = bot
        self.options = options
        
                # Validate that we have options
        if not options:
            raise ValueError("Options are required for ticket panel")
        
        select_options = []
        for idx, option in enumerate(options):
            select_options.append(
                discord.SelectOption(
                    label=option['name'],
                    description=f"Create a {option['name']} ticket",
                    value=option['name'],
                    emoji="🎫"
                )
            )
        
        self.select_menu = discord.ui.Select(
            placeholder="Select a ticket type",
            options=select_options,
            custom_id="ticket_select",
            min_values=1,
            max_values=1
        )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    async def select_callback(self, interaction: discord.Interaction):
        option = next(opt for opt in self.options if opt['name'] == self.select_menu.values[0])
        
        modal = TicketModal(option['questions'], option)
        await interaction.response.send_modal(modal)
        await modal.wait()

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        for role_id in option['roles']:
            role = interaction.guild.get_role(int(role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        channel = await interaction.guild.create_text_channel(
            name=f"{option['name']}-{interaction.user.name}".lower(),
            category=interaction.guild.get_channel(option['category_id']),
            overwrites=overwrites,
            topic=f"Ticket created by {interaction.user}"
        )

        await self.bot.database.execute(
            """INSERT INTO tickets
               (channel_id, user_id, log_channel_id, closed)
               VALUES (?, ?, ?, 0)""",
            (channel.id, interaction.user.id, option.get('log_channel_id'))
        )
        await self.bot.database.commit()

        embed = discord.Embed(
            title=option['embed_title'],
            description=f"{option['embed_description']}\nCreated by: {interaction.user.mention}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        for question, response in zip(option['questions'], modal.responses):
            embed.add_field(
                name=question,
                value=response.value or "No response provided",
                inline=False
            )

        role_mentions = ' '.join(f"<@&{role_id}>" for role_id in option['roles'])
        
        await channel.send(role_mentions, embed=embed)
        await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)
        
        self.select_menu.values.clear()
        await interaction.message.edit(view=self)
