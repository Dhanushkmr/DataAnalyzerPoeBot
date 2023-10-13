from fastapi_poe import make_app
from modal import Image, Stub, Secret, asgi_app
import os
from eda_bot import EDA_bot

bot = EDA_bot()

# The following is setup code that is required to host with modal.com
image = Image.debian_slim().pip_install_from_requirements("requirements.txt")
stub = Stub("DataAnalyzerPoeBot")


@stub.function(image=image, secret=Secret.from_name("poe-access-key"))
@asgi_app()
def fastapi_app():
    app = make_app(bot, access_key=os.environ["POE_BOT_ACCESS_KEY"])
    return app
