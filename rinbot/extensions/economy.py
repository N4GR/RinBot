"""
RinBot's economy command cog

- commands:
    * /orange rank `Shows the Top 10 server leaderboard for the users with most oranges`
    * /orange transfer `Transfer oranges from you and someone else`
    * /orange store `Shows what items that guild has to offer at the store`
    * /orange create-role `Creates a role to be sold on the server's store`
    * /orange buy `Buys an item from the guild's store`
"""

import discord

from discord import app_commands, Interaction
from discord.ext.commands import Cog

from rinbot.base import log_exception, is_hex, hex_to_int
from rinbot.base import DBTable
from rinbot.base import DBColumns
from rinbot.base import respond
from rinbot.base import RinBot
from rinbot.base import Colour
from rinbot.base import text

# from rinbot.base import is_owner
from rinbot.base import is_admin
from rinbot.base import not_blacklisted

# Store packages
from PIL import Image
from io import BytesIO
import aiohttp

class Economy(Cog, name='economy'):
    def __init__(self, bot: RinBot) -> None:
        self.bot = bot
    
    orange = app_commands.Group(
        name=text['ECONOMY_ORANGE_NAME'], description=text['ECONOMY_ORANGE_DESC']
    )
    
    @orange.command(
        name=text['ECONOMY_RANK_NAME'],
        description=text['ECONOMY_RANK_DESC'])
    @not_blacklisted()
    # @is_admin()
    # @is_owner()
    async def _orange_rank(self, interaction: Interaction) -> None:
        currency = await self.bot.db.get(DBTable.CURRENCY,
            condition=f'guild_id={interaction.guild.id}')
        
        try:
            flattened = [(row[1], row[2]) for row in currency]
            sorted_data = sorted(flattened, key=lambda x: x[1], reverse=True)
            users = []
            
            for user in sorted_data[:10]:
                u = self.bot.get_user(user[0] or await self.bot.fetch_user(user[0]))
                users.append(u.name)
            
            rank_data = [
                f'{i}. {item[1]}{text["ECONOMY_CURR_ICON"]} - `{users[i-1]}`'
                for i, item in enumerate(sorted_data[:10], start=1)
            ]
            message = '\n'.join(rank_data)
            
            embed = discord.Embed(
                title=text['ECONOMY_RANK_TOP_10'],
                description=f'{message}',
                colour=Colour.YELLOW
            )
            embed.set_footer(text=text['ECONOMY_BANK'])
            
            await respond(interaction, message=embed)
        except Exception as e:
            log_exception(e)
    
    @orange.command(
        name=text['ECONOMY_TRANSFER_NAME'],
        description=text['ECONOMY_TRANSFER_DESC'])
    @not_blacklisted()
    # @is_admin()
    # @is_owner()
    async def _orange_move(self, interaction: Interaction, member: discord.Member, value: int) -> None:
        if member == interaction.user:
            return await respond(interaction, Colour.RED, text['ECONOMY_TRANSFER_SAME_USER'])
        
        embed = await self.__move_currency(interaction, interaction.user, member, value)
        await respond(interaction, message=embed, hidden=True)
    
    @orange.command(
        name=text['ECONOMY_STORE_NAME'],
        description=text['ECONOMY_STORE_DESC'])
    @not_blacklisted()
    # @is_admin()
    # @is_owner()
    async def _orange_store(self, interaction: Interaction) -> None:
        try:
            store = await self.bot.db.get(DBTable.STORE,
                condition=f'guild_id={interaction.guild.id}')
            
            if not store:
                return await respond(interaction, Colour.RED, text['ECONOMY_STORE_NO_ITEMS'])
            
            items = []
            
            for row in store:
                items.append(f'**{row[2]}** - `{row[3]}`{text["ECONOMY_CURR_ICON"]}')
            
            data = [f'{item}' for item in items]
            data = '\n'.join(data)
            
            await respond(interaction, Colour.YELLOW, f'{data}', text['ECONOMY_STORE_EMBED_TITLE'].format(
                guild=interaction.guild.name
            ), hidden=True)
        except Exception as e:
            log_exception(e)
    
    @orange.command(
        name=text['ECONOMY_BUY_NAME'],
        description=text['ECONOMY_BUY_DESC'])
    @not_blacklisted()
    # @is_admin()
    # @is_owner()
    async def _orange_buy(self, interaction: Interaction, item: str) -> None:
        try:
            item = await self.bot.db.get(DBTable.STORE,
                condition=f'guild_id={interaction.guild.id} AND name="{item}"')
            
            if not item:
                return await respond(interaction, Colour.RED, text['ECONOMY_BUY_INVALID_ITEM'], hidden=True)
            
            member = interaction.guild.get_member(interaction.user.id) or await interaction.guild.fetch_member(interaction.user.id)
            
            await self.__buy_item(interaction, member, item[0])
        except Exception as e:
            log_exception(e)
    
    @orange.command(
        name=text['ECONOMY_ROLE_NAME'],
        description=text['ECONOMY_ROLE_DESC'])
    @app_commands.describe(colour=text['ECONOMY_ROLE_COLOUR'])
    @not_blacklisted()
    @is_admin()
    # @is_owner()
    async def _orange_create_new_role(self, interaction: Interaction, name: str, colour: str, price: int) -> None:
        try:
            if not is_hex(colour):
                return await respond(interaction, Colour.RED, text['ECONOMY_ROLE_INVALID_COLOUR'], hidden=True)
            
            colour = hex_to_int(colour)
            
            try:
                await interaction.guild.create_role(name=name, colour=colour)
            except Exception as e:
                e = log_exception(e)
                return await respond(interaction, Colour.RED, f"{text['ECONOMY_ROLE_CREATION_ERROR']}: {e}", hidden=True)
            
            roles = interaction.guild.roles
            roles_f = {}
            for i in roles:
                roles_f[i.name] = i.id
            
            if name in roles_f.keys():
                new_role = interaction.guild.get_role(roles_f[name])
            else:
                return await respond(interaction, Colour.RED, text['ECONOMY_ROLE_CREATION_ERROR'])
            
            data = {
                'guild_id': interaction.guild.id,
                'id': new_role.id,
                'name': name,
                'price': price,
                'type': 0  # Role type
            }
            
            await self.bot.db.put(DBTable.STORE, data)
            
            await respond(interaction, Colour.GREEN, text['ECONOMY_ROLE_CREATION_SUCCESS'].format(
                role=name
            ), hidden=True)
        except Exception as e:
            log_exception(e)
    
    async def __buy_item(self, interaction: Interaction, member: discord.Member, item):
        try:            
            item_id = item[1]
            name = item[2]
            price = item[3]
            item_type = item[4]
            
            # Role type
            if item_type == 0:
                role = discord.utils.get(interaction.guild.roles, id=int(item_id))
                user_roles = interaction.user.roles
                for user_role in user_roles:
                    if user_role.id == role.id:
                        return await respond(interaction, Colour.RED, text['ECONOMY_ALREADY_HAS_ITEM'])
                if not role:
                    return await respond(interaction, Colour.RED, text['ECONOMY_BUY_NO_ROLE'], hidden=True)
            
            transaction = await self.__remove_currency(interaction, member, price)
            
            if not transaction[0]:
                embed = discord.Embed(
                    title = text['ECONOMY_ERROR_NOT_ENOUGH'],
                    description=text['ECONOMY_CURR_BALANCE'].format(wallet=transaction[1]),
                    colour=Colour.RED
                )
                
                return await respond(interaction, message=embed, hidden=True)
            
            await member.add_roles(role)
            
            embed = discord.Embed(
                title=text['ECONOMY_BUY_SUCCESS'],
                description=text['ECONOMY_BUY_SUCCESS_EMBED'].format(
                    role=name,
                    price=price,
                    balance=transaction[1]
                ),
                colour=Colour.GREEN
            )
            embed.set_footer(text=text['ECONOMY_BANK'])
            
            await respond(interaction, message=embed, hidden=True)
        except Exception as e:
            log_exception(e)
    
    async def __move_currency(self, interaction: Interaction, sender: discord.Member, receiver: discord.Member, value: int) -> discord.Embed:
        try:
            sender_data = await self.bot.db.get(DBTable.CURRENCY,
                condition=f"guild_id={interaction.guild.id} AND user_id={sender.id}")
            receiver_data = await self.bot.db.get(DBTable.CURRENCY,
                condition=f"guild_id={interaction.guild.id} AND user_id={receiver.id}")
            
            sender_wallet = sender_data[0][2]
            receiver_wallet = receiver_data[0][2]
            
            if sender_wallet < value:
                embed = discord.Embed(
                    title=text['ECONOMY_ERROR_NOT_ENOUGH'],
                    description=text['ECONOMY_CURR_BALANCE'].format(wallet=sender_wallet),
                    colour=Colour.RED
                )
            else:
                sender_wallet -= int(value)
                receiver_wallet += int(value)

                await self.bot.db.update(
                    DBTable.CURRENCY, {"wallet": sender_wallet},
                    condition=f"guild_id={interaction.guild.id} AND user_id={sender.id}")
                await self.bot.db.update(
                    DBTable.CURRENCY, {"wallet": receiver_wallet},
                    condition=f"guild_id={interaction.guild.id} AND user_id={receiver.id}")
                
                embed = discord.Embed(
                    title=text['ECONOMY_TRANSFER_SUCCESS'],
                    description=text['ECONOMY_TRANSFER_EMBED'].format(
                        value=f'{value}{text["ECONOMY_CURR_ICON"]}',
                        receiver=receiver.name,
                        wallet=f'{sender_wallet}{text["ECONOMY_CURR_ICON"]}'
                    ),
                    colour=Colour.GREEN
                )
                
            embed.set_footer(text=text['ECONOMY_BANK'])
            
            return embed
        except Exception as e:
            log_exception(e)
    
    async def __remove_currency(self, interaction: Interaction, member: discord.Member, value: int) -> list:
        try:
            member_data = await self.bot.db.get(DBTable.CURRENCY,
                condition=f'guild_id={interaction.guild.id} AND user_id={member.id}')

            member_wallet = member_data[0][2]

            if member_wallet < int(value):
                return [False, member_wallet]

            member_wallet -= int(value)

            await self.bot.db.update(
                DBTable.CURRENCY, {'wallet': member_wallet},
                condition=f'guild_id={interaction.guild.id} AND user_id={member.id}')

            return [True, member_wallet]
        except Exception as e:
            log_exception(e)

    @orange.command(
        name = text["ECONOMY_ADD_ITEM_NAME"],
        description = text["ECONOMY_ADD_ITEM_DESC"])
    @app_commands.choices(type = [
        app_commands.Choice(name = text["ECONOMY_ADD_ITEM_CHOICE"], value = 0),
    ])
    @not_blacklisted()
    @is_admin()
    # @is_owner()
    async def _add_item(self, interaction: Interaction, type: app_commands.Choice[int], name: str, price: int, link: str) -> None:
        await interaction.response.defer(thinking = True)

        async def fail_embed(desc):
            embed = discord.Embed(
                description = f"❌ {desc}", 
                color = Colour.RED
                )

            await interaction.followup.send(embed = embed, ephemeral = True)

        async def fetch_content(url):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        return False

        async def is_image_bytes(content):
            try:
                with Image.open(BytesIO(content)) as img:
                    img.verify()  # Verify that it is an image
                return True
            except (IOError, SyntaxError) as e:
                return False
            
        content = await fetch_content(link)

        # Checks if there's a response
        if content is False:
            await fail_embed(f"The link you sent isn't valid!\n\nYou sent:\n{link}")
            return
        # Checks if the response contains an image
        elif await is_image_bytes(content) is False:
            await fail_embed(f"You didn't send a direct image!\n\nYou sent:\n{link}")
            return
        
        # Opens the badge image in Pillow
        badge = Image.open(BytesIO(content)).convert("RGBA")

        # Checks if the image is a square
        if badge.width != badge.height:
            await fail_embed(f"{text['ECONOMY_ADD_ITEM_ERROR_SQUARE'][0]} {badge.width}{text['ECONOMY_ADD_ITEM_ERROR_SQUARE'][1]} {badge.height}{text['ECONOMY_ADD_ITEM_ERROR_SQUARE'][2]}")
            return
        
        # Resizes the image to a 64x64
        badge = badge.resize((64, 64), resample = Image.Resampling.LANCZOS)

        # Getting image blob object
        with BytesIO() as buffer:
            badge.save(buffer, format = "PNG")
            imagebytes = buffer.getvalue()

        guild_badge_vault = self.bot.db.get(DBTable.STORE, f"{DBColumns.store.GUILD_ID.value} = {interaction.guild.id}")

        # Counts how many items are in the store to set as ID and checks if the blob is already there or not.
        counter = 0
        for id in await guild_badge_vault:
            counter =+ 1
            if imagebytes == id[5]:
                await fail_embed(f"The image you requested to add is already in the guild store!")
                return

        # Adds the badge to the guild store with the id set to max id number + 1
        await self.bot.db.put(DBTable.STORE, {
            "guild_id": interaction.guild.id,
            "id": counter + 1,
            "name": name,
            "price": price,
            "type": type.value,
            "data": imagebytes
        })

        # Success message
        embed = discord.Embed(
            title = text["ECONOMY_ADD_ITEM_SUCCESS"], 
            color = Colour.GREEN
            )
        
        embed.add_field(name = text["ECONOMY_ADD_ITEM_EMBED_BADGE_NAME"], value = name, inline = True)
        embed.add_field(name = text["ECONOMY_ADD_ITEM_EMBED_PRICE_NAME"], value = str(price), inline = True)
        embed.add_field(name = text["ECONOMY_ADD_ITEM_EMBED_LINK_USED_NAME"], value = link, inline = False)
        embed.set_image(url = link)
        embed.set_footer(text = f"{interaction.guild.name.upper()} | {interaction.guild.id}")

        await interaction.followup.send(embed = embed, ephemeral = True)

# SETUP
async def setup(bot: RinBot):
    await bot.add_cog(Economy(bot))
