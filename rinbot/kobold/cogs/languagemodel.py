import discord, os
from rinbot.base.logger import logger
from rinbot.base.client import RinBot
from rinbot.base.json_loader import get_conf
from rinbot.kobold.custom_memory import CustomBufferWindowMemory
from langchain.prompts.prompt import PromptTemplate
from langchain.chains.conversation.base import ConversationChain
from discord.ext import commands

config = get_conf()

CHAT_HISTORY_LINE_LIMIT = 15
CHAR_NAME = config["AI_NAME"]

STOP_SEQUENCES = "Artyom,AusBoss,\\n\\n,<END>,You"
STOP_SEQUENCES = STOP_SEQUENCES.replace("\\n", "\n")
STOP_SEQUENCES = STOP_SEQUENCES.split(",")

def embedder(msg):
    embed = discord.Embed(description=f"{msg}", color=0x9C84EF)
    return embed

# Black magic
class Chatbot:
    def __init__(self, bot: RinBot):
        self.bot = bot
        self.prompt = None
        self.endpoint = bot.endpoint
        self.llm = self.bot.llm
        self.histories = {}
        self.stop_sequences = {}
        self.convo_filename = None
        self.conversation_history = ""
        self.char_name = CHAR_NAME

    async def get_messages_by_channel(self, channel_id):
        channel = self.bot.get_channel(int(channel_id))
        messages = []
        async for message in channel.history(limit=None):
            if message.content.startswith(".") or message.content.startswith("/"):
                continue
            messages.append((
                    message.author.display_name,
                    message.channel.id,
                    message.clean_content.replace("\n", " "),))
            if len(messages) >= CHAT_HISTORY_LINE_LIMIT:
                break
        return messages[:CHAT_HISTORY_LINE_LIMIT]

    async def detect_and_replace_out(self, message_content):
        if f"\n{self.char_name}:":
            message_content = message_content.replace(f"\n{self.char_name}:", "")
        return message_content

    async def detect_and_replace_in(self, message_content):
        if f"@{self.char_name}":
            message_content = message_content.replace(f"@{self.char_name}", "")
        return message_content

    async def get_memory_for_channel(self, channel_id):
        channel_id = str(channel_id)
        if channel_id not in self.histories:
            self.histories[channel_id] = CustomBufferWindowMemory(
                k=CHAT_HISTORY_LINE_LIMIT, ai_prefix=self.char_name)
            messages = await self.get_messages_by_channel(channel_id)
            messages_to_add = messages[-2::-1]
            messages_to_add_minus_one = messages_to_add[:-1]
            for message in messages_to_add_minus_one:
                name = message[0]
                channel_ids = str(message[1])
                message = message[2]
                logger.info(f"{name}: {message}")
                await self.add_history(name, channel_ids, message)
        return self.histories[channel_id]

    async def get_stop_sequence_for_channel(self, channel_id, name):
        name_token = f"\n{name}:"
        if channel_id not in self.stop_sequences:
            self.stop_sequences[channel_id] = STOP_SEQUENCES
        if name_token not in self.stop_sequences[channel_id]:
            self.stop_sequences[channel_id].append(name_token)
        return self.stop_sequences[channel_id]

    async def set_convo_filename(self, convo_filename):
        self.convo_filename = convo_filename
        if not os.path.isfile(convo_filename):
            with open(convo_filename, "w", encoding="utf-8") as f:
                f.write("<START>\n")
        with open(convo_filename, "r", encoding="utf-8") as f:
            lines = f.readlines()
            num_lines = min(len(lines), self.bot.num_lines_to_keep)
            self.conversation_history = "<START>\n" + "".join(lines[-num_lines:])

    async def generate_response(self, message, message_content) -> None:
        channel_id = str(message.channel.id)
        name = message.author.display_name
        memory = await self.get_memory_for_channel(str(channel_id))
        stop_sequence = await self.get_stop_sequence_for_channel(channel_id, name)
        logger.info(f"[AI]-[INFO]: Stop sequences: {stop_sequence}")
        formatted_message = f"{name}: {message_content}"
        MAIN_TEMPLATE = f"""
            {{history}}
            {{input}}
            {self.char_name}:"""
        PROMPT = PromptTemplate(
            input_variables=["history", "input"], template=MAIN_TEMPLATE)
        conversation = ConversationChain(
            prompt=PROMPT, llm=self.llm, verbose=True, memory=memory,)
        input_dict = {"input": formatted_message, "stop": stop_sequence}
        response_text = conversation(input_dict)
        
        for stop_token in stop_sequence:
            if stop_token in response_text["response"]:
                response_text["response"] = response_text["response"].split(stop_token)[0]
                break
        
        response = await self.detect_and_replace_out(response_text["response"])
        with open(self.convo_filename, "a", encoding="utf-8") as f:
            f.write(f"{message.author.display_name}: {message_content}\n")
            f.write(f"{self.char_name}: {response_text}\n")
        return response

    async def add_history(self, name, channel_id, message_content) -> None:
        memory = await self.get_memory_for_channel(str(channel_id))
        formatted_message = f"{name}: {message_content}"
        logger.info(f"[AI]-[INFO]: Adding message to memory: {formatted_message}")
        memory.add_input_only(formatted_message)
        return None

class ChatbotCog(commands.Cog, name="chatbot"):
    def __init__(self, bot: RinBot):
        self.bot = bot
        self.chatlog_dir = bot.chatlog_dir
        self.chatbot = Chatbot(bot)
        if not os.path.exists(self.chatlog_dir):
            os.makedirs(self.chatlog_dir)

    @commands.hybrid_command(name="chat")
    async def chat(self, message: discord.Message, message_content) -> None:
        if message.guild:
            server_name = message.channel.name
        else:
            server_name = message.author.name
        chatlog_filename = os.path.join(
            self.chatlog_dir, f"{server_name}_ai_chatlog.log")
        if (
            message.guild
            and self.chatbot.convo_filename != chatlog_filename
            or not message.guild
            and self.chatbot.convo_filename != chatlog_filename):
            await self.chatbot.set_convo_filename(chatlog_filename)
        response = await self.chatbot.generate_response(message, message_content)
        return response

# SETUP
async def setup(bot: RinBot):
    await bot.add_cog(ChatbotCog(bot))
