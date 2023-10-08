# Welcome to the Poe server bot quick start. This repo includes starter code that allows you to
# quickly get a bot running. By default, the code uses the EchoBot, which is a simple bot that
# echos a message back at its user and is a good starting point for your bot, but you can
# comment/uncomment any of the following code to try out other example bots or build on top
# of the EchoBot.

from fastapi_poe import make_app
from modal import Image, Stub, asgi_app
from eda_bot import EDA_bot

# Echo bot is a very simple bot that just echoes back the user's last message.
bot = EDA_bot()

# The following is setup code that is required to host with modal.com
image = Image.debian_slim().pip_install_from_requirements("requirements.txt")
# Rename "poe-server-bot-quick-start" to your preferred app name.
stub = Stub("poe-server-bot-quick-start")


@stub.function(image=image)
@asgi_app()
def fastapi_app():
    # Optionally, provide your Poe access key here:
    # 1. You can go to https://poe.com/create_bot?server=1 to generate an access key.
    # 2. We strongly recommend using a key for a production bot to prevent abuse,
    # but the starter example disables the key check for convenience.
    # 3. You can also store your access key on modal.com and retrieve it in this function
    # by following the instructions at: https://modal.com/docs/guide/secrets
    # POE_ACCESS_KEY = ""
    # app = make_app(bot, access_key=POE_ACCESS_KEY)
    app = make_app(bot, allow_without_key=True)
    return app
