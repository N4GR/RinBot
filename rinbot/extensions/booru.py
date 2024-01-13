"""
#### RinBot's booru command cog
- Commands:
    * /booru random `Shows a random picture from danbooru with the given tags and rating`
"""

# Imports
from __future__ import unicode_literals
import discord, random, os
from discord import Interaction
from discord import app_commands
from discord.ext.commands import Bot, Cog
from discord.app_commands import Group
from discord.app_commands.models import Choice
from rinbot.base.checks import *
from rinbot.booru import Danbooru
from rinbot.base.helpers import load_lang, format_exception
from rinbot.base.colors import *
from random import randint

# Verbose
text = load_lang()

# Load config
CONFIG_PATH = f"{os.path.realpath(os.path.dirname(__file__))}/../config/config-rinbot.json"
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as c: config = json.load(c)
except Exception as e:
    logger.critical(f"{format_exception(e)}")
    sys.exit()

# Load vals
UNAME=config["BOORU_USERNAME"]
API=config["BOORU_KEY"]
IS_GOLD=config["BOORU_IS_GOLD"]

# "booru" command block
class Booru(Cog, name="booru"):
    def __init__(self, bot):
        self.bot:Bot = bot
    
    # Command groups
    booru = Group(name=text['BOORU_NAME'], description=text['BOORU_DESC'])
    
    # Booru random
    @booru.command(
        name=text['BOORU_RANDOM_NAME'],
        description=text['BOORU_RANDOM_DESC'])
    @app_commands.choices(
        rating=[
            Choice(name=f"{text['BOORU_RANDOM_RATING_G']}", value="g"),
            Choice(name=f"{text['BOORU_RANDOM_RATING_S']}", value="s"),
            Choice(name=f"{text['BOORU_RANDOM_RATING_Q']}", value="q")])
    @not_blacklisted()
    async def booru_random(self, interaction:Interaction, rating:Choice[str]=None, tags:str=None) -> None:
        
        # If a rating is not provided
        if not rating:
            embed = discord.Embed(
                description=f"{text['BOORU_RANDOM_NO_RAT']}",
                color=0xd91313)
            return await interaction.response.send_message(embed=embed)
        
        # Split tags and check how many there are
        tag_count = tags.split(" ")
        
        if len(tag_count) >= 3 and not IS_GOLD:
            embed = discord.Embed(
                description=f"{text['BOORU_RANDOM_MAX_API']}",
                color=0xd91313)
            return await interaction.response.send_message(embed=embed)
        elif len(tag_count) >= 6:
            embed = discord.Embed(
                description=f"{text['BOORU_RANDOM_MAX_API_GOLD']}",
                color=0xd91313)
            return await interaction.response.send_message(embed=embed)
        
        # Do the thing
        await interaction.response.defer()
        try:
            try:
                client = Danbooru('danbooru', username=UNAME, api_key=API)
                posts = client.post_list(tags=f'rating:{rating.value}'
                                        if not tags else tags, pages=randint(1, 1000), limit=1000)
                post = random.choice(posts)
                try: url = post['file_url']
                except: url = post['source']
                embed = discord.Embed(color=0x9f17d1)
                embed.set_image(url=url)
                await interaction.followup.send(embed=embed)
            except IndexError:
                embed = discord.Embed(
                    description=f"{text['BOORU_RANDOM_EMPTY_RESPONSE']}",
                    color=RED)
                return await interaction.followup.send(embed=embed)
        except Exception as e:
            e = format_exception(e)
            embed = discord.Embed(
                title=f"{text['BOORU_RANDOM_API_ERROR']}",
                description=f"{e}",
                color=RED)
            return await interaction.followup.send(embed=embed)

# SETUP
async def setup(bot:Bot):
    await bot.add_cog(Booru(bot))